import pprint
import json
import time
from time import sleep
from typing import List, Optional, Tuple
from collections import Counter
import concurrent.futures

import numpy
import requests

from simulations.azure_helper import create_machines, start_machines, stop_machines, get_vm_ips, exec_command
from simulations.reduce_graph import choose_routes

SAMPLES = 40
PARAMETERS_FILE = '/home/azureuser/privacy_in_pcn/client/src/client/parameters.py'
PULL_CMD = 'git reset origin/master --hard && (git pull || echo true)'
COMPILE_ENCLAVE_CMD = ". /opt/intel/sgxsdk/environment && make clean && make SGX_MODE=HW SGX_DEBUG=0 SGX_PRERELEASE=1"
SKIP_ENCLAVE_CMD = f'echo "SKIP_ENCLAVE = False\nBULK_SEND = True" > {PARAMETERS_FILE}'
RESET_RELAY_CMD = 'sudo systemctl restart pcn'
RESET_ENCLAVE_CMD = 'sudo systemctl restart pcn-enclave'

ip_to_name = {}


def get_pull_cmd(should_skip_enclave: bool = False, should_compile: bool = False, bulk_send: bool = True):
    parameters = f"SKIP_ENCLAVE = {should_skip_enclave}\nBULK_SEND = {bulk_send}"
    cmd = f'cd privacy_in_pcn && {PULL_CMD}'
    cmd += f' && echo "{parameters}" > {PARAMETERS_FILE}'
    cmd += f" && {RESET_RELAY_CMD}"
    if should_compile:
        cmd += f' && {COMPILE_ENCLAVE_CMD}'
    cmd += f' && {RESET_ENCLAVE_CMD}'
    return cmd


def get_names(ips: List[str], insists=True):
    first_insist = True
    for ip in ips:
        while True:
            try:
                name = requests.get(f"http://{ip}/get-name", timeout=2).content.decode()
                ip_to_name[ip] = name
                break
            except Exception as e:
                if not insists:
                    raise
                if not first_insist:
                    print(f"get_names: insisting ({ip}) ({e.__class__.__name__})")
                first_insist = False
                sleep(2)


def connect_clique(ips: List[str]):
    for ip in ips:
        current_dict = {v: k for k, v in ip_to_name.items() if k != ip}
        requests.post(f"http://{ip}/register", json=current_dict)


def reset_and_prepare_system(ips: List[str], should_send: bool = True):
    exec_command(RESET_RELAY_CMD, ips)
    exec_command(RESET_ENCLAVE_CMD, ips)
    sleep(1)
    prepare_clique(ips)
    sleep(0.5)
    if should_send:
        send_payment(ips)


def send_payment(ips: List[str], counts: List[int] = None, continues: bool = False):
    counts = counts or [3]
    route = ','.join(ip_to_name[ip] for ip in ips)
    while True:
        try:
            method = 'initiate-bob-throughput' if continues else 'be-bob-many'
            requests.get(f"http://{ips[-1]}/{method}/{route}/{'/'.join(map(str, counts))}", timeout=30)
            return
        except Exception as e:
            print("send_payment: insisting", e)
            sleep(1)


def get_alice_timing(alice_ip, start_time: Optional[float] = None, many=False):
    first_zero = True
    start_time = start_time or 0
    while True:
        try:
            result = json.loads(requests.get(f"http://{alice_ip}/get-times").content)
            found = len([t for t in result if t[1] and t[0] > start_time])
            data = [t[1] - t[0] for t in result if t[1]]
            if all(r[1] for r in result) or (many and (found / len(result) > 0.95)):
                return numpy.average(data), numpy.std(data)
        except ZeroDivisionError as e:
            if first_zero:
                first_zero = False
            else:
                print(e)
        except Exception as e:
            print(e)
        sleep(5)


def prepare_globals(number_of_machines: int, cmd: Optional[str] = None):
    vm_ips = get_vm_ips(number_of_machines)
    print("ips:", vm_ips)
    if cmd:
        exec_command(cmd, vm_ips)
    prepare_clique(vm_ips)
    print('Finish global preparations')
    return vm_ips


def prepare_clique(ips: List[str]):
    ip_to_name.clear()
    get_names(ips)
    connect_clique(ips)


def _build_throughput_raw_data(concurrent_payments: List[int], ips: List[str], interval=1, samples=SAMPLES):
    """
    Returns tuple with:
        * throughput per second
        * latency per second
    """
    send_payment(ips, concurrent_payments, continues=True)
    resolved, latency = _get_times(ips[0], interval, samples)
    # print("Raw data:", resolved, latency)
    return resolved, latency


def _get_times(alice_ip: str, interval=1, samples=SAMPLES):
    resolved: List[float] = []
    latency: List[float] = []
    sleep(interval * 5)
    for i in range(samples):
        try:
            result = requests.get(f"http://{alice_ip}/get-times", timeout=interval * 2).json()
            done_payments = [t[1] - t[0] for t in result]
            resolved.append(len(done_payments) / interval)
            if done_payments:
                latency.append(numpy.average(done_payments))
        except requests.exceptions.ReadTimeout:
            print("X", end="", flush=True)
        if i % 3 == 0:
            print(".", end="", flush=True)
        sleep(1)
    return resolved, latency


def _get_times_single(alice_ip: str, period: int = 60) -> Tuple[float, float, float]:
    resolved: float = 0
    latency: float = 0
    std: float = 0
    sleep(period)
    try:
        result = requests.get(f"http://{alice_ip}/get-times", timeout=period * 1.5).json()
        done_payments = [t[1] - t[0] for t in result if t[0] and t[1]]
        end_times = sorted([t[1] for t in result if t[1]])
        if len(end_times) > 10:
            resolved = len(end_times) / (max(end_times) - min(end_times))
            std = float(numpy.std(sorted(Counter([int(t) for t in end_times]).values())[2:]))
        if done_payments:
            latency = numpy.average(sorted(done_payments)[5:-5] or done_payments)
    except requests.exceptions.ReadTimeout:
        print("X", end="", flush=True)
        return 0, 0, 0
    return resolved, std, latency


def _build_throughput_summary_data(concurrent_payments: List[int], ips: List[str], interval=1, samples=SAMPLES):
    """
    Returns tuple with:
        * Average throughput
        * standard deviation of throughput
        * Average latency
        * standard deviation of latency
    """
    resolved, latency = _build_throughput_raw_data(concurrent_payments, ips, interval, samples)
    resolved, latency = sorted(resolved)[1:-1], sorted(latency)[1:-1]
    result = numpy.average(resolved), numpy.std(resolved), numpy.average(latency), numpy.std(latency)
    print(f"Throughput result for {concurrent_payments}: {result}, raw data: {resolved}")
    return result


def build_linear_throughput_data(ips: List[str]):
    results = {}
    for concurrent_payments in [1] + list(range(50, 1_051, 50)):
        reset_and_prepare_system(ips)
        results[concurrent_payments] = _build_throughput_summary_data([concurrent_payments], ips)
    return results


def build_x_throughput_data(ips: List[str]):
    ips = ips[:5]
    assert len(ips) == 5
    results = {}
    for concurrent_payments in [1] + list(range(100, 551, 75)):
        reset_and_prepare_system(ips)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future1 = executor.submit(_build_throughput_summary_data, [concurrent_payments], [ips[0], ips[4], ips[1]])
            future2 = executor.submit(_build_throughput_summary_data, [concurrent_payments], [ips[2], ips[4], ips[3]])
            results[concurrent_payments] = {
                "1": future1.result(),
                "2": future2.result(),
            }
    return results


def build_dynamic_x_throughput_data(ips: List[str]):
    ips = ips[:5]
    assert len(ips) == 5
    results = []
    for _ in range(7):
        reset_and_prepare_system(ips)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future1 = executor.submit(_build_throughput_raw_data, [100, 600], [ips[0], ips[4], ips[1]])
            future2 = executor.submit(_build_throughput_raw_data, [600], [ips[2], ips[4], ips[3]])
            results.append({
                "1": future1.result(),
                "2": future2.result(),
            })
    return results


def build_latency_data(ips: List[str]):
    to_return = {}
    _ = get_alice_timing(ips[0])
    for length in range(2, len(ips) + 1):
        reset_and_prepare_system(ips)
        times = []
        for _ in range(10):
            start_time = time.time()
            send_payment(ips)
            t, _ = get_alice_timing(ips[0], start_time=start_time)
            times.append(t)
            sleep(0.1)
        avg, std = numpy.average(times), numpy.std(times)
        print(f"for concurrent {length} the avg is: {(avg, std)}")
        to_return[length] = (avg, std)
    return to_return


def build_lightning_data(ips, concurrent_payment=450):
    results = {}
    for topology_size in [6, 9, 13, 16, 19, 22, 24]:
        routes = choose_routes(number_of_nodes=topology_size)
        routes = [[ips[node_index] for node_index in route] for route in routes]
        reset_and_prepare_system(ips, should_send=False)
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(routes)) as executor:
            [executor.submit(send_payment, route, [concurrent_payment], continues=True) for route in routes]
            futures = [executor.submit(_get_times_single, ip) for ip in ips[:topology_size]]
            results[topology_size] = [f.result() for f in futures]
            print(results[topology_size])
    return results


if __name__ == '__main__':
    # create_machines(range(0, 4), 'eastus')
    # create_machines(range(0, 4), 'northeurope')
    start_machines(6)
    machine_ips = prepare_globals(6, get_pull_cmd(should_compile=True))
    for route_length in range(4, 7):
        print("route_length:", route_length)
        result = build_linear_throughput_data(machine_ips[:route_length])
        print('-' * 50)
        print("Final output")
        print('-' * 50)
        print(result)
    # print(build_x_throughput_data(machine_ips))
    # print(build_dynamic_x_throughput_data(machine_ips))
    # pprint.pprint(build_lightning_data(machine_ips), width=1000)
    stop_machines(6)
