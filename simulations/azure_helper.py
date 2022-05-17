import concurrent.futures
import time
from typing import List

from azure.common.client_factory import get_client_from_cli_profile
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.network import NetworkManagementClient
import paramiko
import warnings

warnings.filterwarnings(action='ignore', module='.*paramiko.*')

GROUP_NAME = "privacy-in-pcn"
_REGIONS = ["eastus", "northeurope", "westus"]
IMAGE_VERSIONS = {"eastus": '0.0.9', "westus": '0.0.9', "northeurope": '0.0.9'}
IMAGE = "/subscriptions/103d5f0d-ba93-41e0-9ff0-e70dfb790202/resourceGroups/privacy-in-pcn/providers/Microsoft.Compute/galleries/privacy_in_pcn_gallery/images/privacy-in-pcn-definition/versions/{version}"

REGIONS_TO_USE = 2


def get_location(region: str) -> str:
    return region + ("2" if region == "westus" else "")


def get_image(region: str) -> str:
    return IMAGE.format(version=IMAGE_VERSIONS[region])


def create_nic(index: int, region: str):
    """
    Note here we assume that there already exist (with the default configuration):
    * virtual network with the name `pcn-location`
    * network security groups with the name `pcn-location-0-nsg`
    * a snapshot of the machine
    """
    network_client = get_client_from_cli_profile(NetworkManagementClient)

    print("Creating public IP")
    poller = network_client.public_ip_addresses.create_or_update(
        GROUP_NAME,
        f"pcn-ip-{region}-{index}",
        {
            "location": get_location(region),
            "sku": {"name": "Basic"},
            "public_ip_allocation_method": "Dynamic",
            "public_ip_address_version": "IPV4"
        }
    )

    ip_address_result = poller.result()

    poller = network_client.network_interfaces.create_or_update(
        GROUP_NAME,
        f"pcn-nic-{region}-{index}",
        {
            "location": get_location(region),
            "ip_configurations": [{
                "name": f"privacy-in-pcn-ip-config-{region}-{index}",
                "subnet": {
                    "id": f'/subscriptions/103d5f0d-ba93-41e0-9ff0-e70dfb790202/resourceGroups/privacy-in-pcn/providers/Microsoft.Network/virtualNetworks/pcn-{region}/subnets/default'},
                "public_ip_address": {
                    "id": ip_address_result.id}
            }],
            'network_security_group': {
                'id': f"/subscriptions/103d5f0d-ba93-41e0-9ff0-e70dfb790202/resourceGroups/privacy-in-pcn/providers/Microsoft.Network/networkSecurityGroups/pcn-{region}-0-nsg"
            }
        }
    )

    poller.result()


def create_machines(range_indices, region: str = 'eastus'):
    """
    Tutorial to create all the predefined resources:
    https://github.com/Azure-Samples/Hybrid-Compute-Python-Manage-VM/blob/master/example.py
    * resource-group
    """
    compute_client = get_client_from_cli_profile(ComputeManagementClient)

    async_vm_creation = []
    for index in range_indices:
        create_nic(index, region)
        # Create Linux VM
        print('\nCreating Linux Virtual Machine')
        async_vm_creation.append(compute_client.virtual_machines.create_or_update(GROUP_NAME, f"pcn-{region}-{index}", {
            'location': get_location(region),
            'os_profile': {
                'computer_name': f"pcn-{region}-{index}",
                'admin_username': "azureuser",
                'admin_password': "AzureUser123!@#"
            },
            'hardware_profile': {
                'vm_size': 'Standard_DC1s_v2'
            },
            'storage_profile': {
                'image_reference': {
                    'id': get_image(region)
                },
            },
            'network_profile': {
                'network_interfaces': [{
                    'id': f"/subscriptions/103d5f0d-ba93-41e0-9ff0-e70dfb790202/resourceGroups/privacy-in-pcn/providers/Microsoft.Network/networkInterfaces/pcn-nic-{region}-{index}",
                }]
            },
        }))
    [creation.wait() for creation in async_vm_creation]


def get_vm_names(count, number_of_regions=REGIONS_TO_USE):
    vm_names = []
    for i in range(16):
        region = _REGIONS[i % number_of_regions]
        vm_names.append(f"pcn-{region}-{i // number_of_regions}")
    for i in range(8, 16):
        vm_names.append(f"pcn-eastus-{i}")
    return vm_names[:count]


def start_machines(count=3):
    compute_client = get_client_from_cli_profile(ComputeManagementClient)
    available_machines = {vm.name for vm in compute_client.virtual_machines.list_all()}
    l = []
    for vm_name in get_vm_names(count):
        if vm_name not in available_machines:
            raise Exception(f"Machine does not exists: {vm_name}")
        l.append(compute_client.virtual_machines.start(GROUP_NAME, vm_name))
    [a.wait() for a in l]


def get_vm_ips(count=3):
    compute_client = get_client_from_cli_profile(ComputeManagementClient)
    network_client = get_client_from_cli_profile(NetworkManagementClient)

    ips = []
    for vm_name in get_vm_names(count):
        vm_instance = compute_client.virtual_machines.get(GROUP_NAME, vm_name)
        interface = vm_instance.network_profile.network_interfaces[0].id
        pub_ip = network_client.network_interfaces.get(GROUP_NAME, interface.split('/')[-1]).ip_configurations[
            0].public_ip_address.id
        ip = network_client.public_ip_addresses.get(GROUP_NAME, pub_ip.split('/')[-1]).ip_address
        ips.append(ip)
    return ips


def stop_machines(count=3):
    compute_client = get_client_from_cli_profile(ComputeManagementClient)

    l = []
    for vm_name in get_vm_names(count):
        l.append(compute_client.virtual_machines.deallocate(GROUP_NAME, vm_name))
    [a.wait() for a in l]


def _exec(t):
    cmd, ip = t
    for _ in range(5):
        try:
            c = paramiko.SSHClient()
            c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            c.connect(hostname=ip, username="azureuser", password="AzureUser123!@#")
            session = c.get_transport().open_session(timeout=60)
            session.exec_command(cmd)
            if session.recv_exit_status() != 0:
                raise Exception(f"FAILED to pull on {ip}: {session.in_stderr_buffer.read(65536)}")
            return True
        except Exception as e:
            print(f"Insisnting: exec_command ({ip}: {cmd})", str(e))
            time.sleep(1)
    raise Exception(f"Failed to execute command: {ip}: {cmd}")


def exec_command(cmd: str, ips: List[str]):
    with concurrent.futures.ProcessPoolExecutor() as executor:
        [a.result() for a in [executor.submit(_exec, (cmd, ip)) for ip in ips]]


if __name__ == '__main__':
    create_machines([8], region='eastus')
    create_machines([8], region='northeurope')
