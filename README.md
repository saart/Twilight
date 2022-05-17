# Implementation of the paper "Differentially-Private Payment Channels with Twilight"
In this repo we implemented the three parts: 
* Smart contract
* Enclave
* Relay
* Noise simulations: liquidity_distribution.py to create the stationary distribution per liquidity per sigma, and success_rate to compute the graph.
* Other graphs: adoption, efficiency-privacy tradeoff, channel-disjoint routes.

# Prerequisites:
* Ubuntu* Desktop-16.04-LTS 64bits
* Intel SGX2 Hardware
* 6th Generation Intel(R) Core(TM) Processor or newer (only if you want to run it in hardware mode, otherwise run in software/simulation mode)
## How to install on a new Azure confidetial computing machine
```
// Prepare machine (https://docs.microsoft.com/en-us/azure/confidential-computing/quick-create-portal)
echo 'deb [arch=amd64] https://download.01.org/intel-sgx/sgx_repo/ubuntu bionic main' | sudo tee /etc/apt/sources.list.d/intel-sgx.list
wget -qO - https://download.01.org/intel-sgx/sgx_repo/ubuntu/intel-sgx-deb.key | sudo apt-key add -
echo "deb http://apt.llvm.org/bionic/ llvm-toolchain-bionic-7 main" | sudo tee /etc/apt/sources.list.d/llvm-toolchain-bionic-7.list
wget -qO - https://apt.llvm.org/llvm-snapshot.gpg.key | sudo apt-key add -
echo "deb [arch=amd64] https://packages.microsoft.com/ubuntu/18.04/prod bionic main" | sudo tee /etc/apt/sources.list.d/msprod.list
wget -qO - https://packages.microsoft.com/keys/microsoft.asc | sudo apt-key add -
dmesg | grep -i sgx
sudo apt update && sudo apt -y install dkms

wget https://download.01.org/intel-sgx/sgx-dcap/1.7/linux/distro/ubuntu18.04-server/sgx_linux_x64_driver_1.35.bin -O sgx_linux_x64_driver.bin && chmod +x sgx_linux_x64_driver.bin && sudo ./sgx_linux_x64_driver.bin 
sudo apt -y install clang-8 libssl-dev gdb libsgx-enclave-common libprotobuf10 libsgx-dcap-ql libsgx-dcap-ql-dev az-dcap-client open-enclave make build-essential ocaml ocamlbuild automake autoconf libtool wget python libssl-dev git cmake perl unzip ocaml-nox ocamlbuild autoconf libtool libcurl4-openssl-dev protobuf-compiler libprotobuf-dev debhelper cmake reprepro python3-pip rapidjson-dev


// Install SDK (https://github.com/intel/linux-sgx)
git clone https://github.com/intel/linux-sgx.git && cd linux-sgx && make preparation
sudo cp external/toolset/ubuntu18.04/{as,ld,ld.gold,objdump} /usr/local/bin && which as ld ld.gold objdump
make sdk && make sdk_install_pkg
cd linux/installer/bin && sudo ./sgx_linux_x64_sdk_2.13.103.1.bin  // then "no" "/opt/intel"
echo "source /opt/intel/sgxsdk/environment" >> ~/.bashrc && bash && cd ~

// install pistache
sudo pip3 install meson ninja setuptools pip -U && git clone https://github.com/pistacheio/pistache.git && cd pistache
/usr/local/bin/meson setup build --buildtype=release -DPISTACHE_USE_SSL=true -DPISTACHE_BUILD_EXAMPLES=true -DPISTACHE_BUILD_TESTS=true -DPISTACHE_BUILD_DOCS=false --prefix=$PWD/prefix && /usr/local/bin/meson compile -C build && /usr/local/bin/meson install -C build
echo """PKG_CONFIG_PATH=$PKG_CONFIG_PATH:/home/azureuser/pistache/build/meson-private/\nLD_LIBRARY_PATH=$LD_LIBRARY_PATH:/home/azureuser/pistache/prefix/lib/x86_64-linux-gnu""" >> ~/.bashrc && bash && cd ~

// Our scripts
cd ~
python3 -m pip install matplotlib==3.3.4 seaborn==0.11.1 starlette uvicorn pycryptodome flask ecpy azure-mgmt-resource==2.0 azure-mgmt-network==2.2 azure-mgmt-compute==4.3 azure-identity logzio-python-handler gunicorn
git config --global alias.co checkout && git config --global alias.st status
git config --global credential.helper store
git clone https://github.cs.huji.ac.il/saart/privacy_in_pcn.git
cd privacy_in_pcn && make SGX_MODE=HW SGX_DEBUG=0 SGX_PRERELEASE=1

// check that the enclave works:
./app -h 39ac9ae97b232b7c024f02b0f9c3e71977c4fe97727484ddd047a5d22b6c1a8164ff83d0c4a02aa1728f36186fec8c05d6fe4beaf5a02415cbd063d1cb0a23a9 -c 1BF4ED8F378ED3D8885CA71808D785BC274E5C0A -l 100 -k 04A6E218A52D79346D4E295056BC7DAAD6A8A25E
curl "http://localhost:9080/?bob_dh_pub=3cdf3d3ea65414296c101cf5b5a584de189e172ffcaac8c9cba13a0cdafc3d435cc25a8d6d4e74598d0b8a9c91113e56985f0f6ec2d7ded8b54612fde31eb7da&encrypted_given_ammount=cad91b154e4bd63a3d84b8de1f60b65dae299565&encrypted_key=d58b1482dce87cd6d8963696410b4e4b5fcf6b31&prev_liquidity=100"

// running the client
echo """[Unit]
Description=privacy-in-pcn relay

[Service]
ExecStart=/home/azureuser/privacy_in_pcn/client/src/client/execute.sh

[Install]
WantedBy=multi-user.target""" > temp_service && sudo mv temp_service /etc/systemd/system/pcn.service
sudo systemctl enable pcn

// running the enclave
echo """[Unit]
Description=privacy-in-pcn enclave

[Service]
ExecStart=/home/azureuser/privacy_in_pcn/App/execute.sh

[Install]
WantedBy=multi-user.target""" > temp_service && sudo mv temp_service /etc/systemd/system/pcn-enclave.service
sudo systemctl enable pcn-enclave
```

# Building
`make` for simple simulation mode (unsecure)

`make SGX_MODE=HW SGX_DEBUG=0 SGX_PRERELEASE=1` for hardware mode

# Running The Enclave
For the secret `123`, the public key is: `39ac9ae97b232b7c024f02b0f9c3e71977c4fe97727484ddd047a5d22b6c1a8164ff83d0c4a02aa1728f36186fec8c05d6fe4beaf5a02415cbd063d1cb0a23a9`.

`./app -h 39ac9ae97b232b7c024f02b0f9c3e71977c4fe97727484ddd047a5d22b6c1a8164ff83d0c4a02aa1728f36186fec8c05d6fe4beaf5a02415cbd063d1cb0a23a9 -c 1BF4ED8F378ED3D8885CA71808D785BC274E5C0A -l 100 -k 04A6E218A52D79346D4E295056BC7DAAD6A8A25E` to execute a test run (note: -h, bob DH public key, must be on the curve. Otherwise we will exit with a failure).

Moreover, with `-p` the enclave can get previous pending payments, and compare to the remaining liquidity. The pending payments should be of the format: `<output><key>#<output><key>...`. Taking the above command, `./app -h 02E7A07A6F51550555271E55A35CC3E79E0457F905000000B916F72F5CDB0E615CE9333457B48EE8970CF0C400000000 -c 1BF4ED8F378ED3D8885CA71808D785BC274E5C0A -l 100 -k 04A6E218A52D79346D4E295056BC7DAAD6A8A25E -p 1BF4ED8F378ED3D8885CA71808D785BC274E5C0A04A6E218A52D79346D4E295056BC7DAAD6A8A25E#1BF4ED8F378ED3D8885CA71808D785BC274E5C0A04A6E218A52D79346D4E295056BC7DAAD6A8A25E` will fail to deliver for liquidity <30, but will succeed for liquidity >30.
Another option is to store a state (which the enclave returns in the end of each execution). Then, in the next request, we should include only changes in the pending payment from the previous state. It can be done by adding "0" to added payments, or "1" to substracted payments. Providing this state can be done using `-s`.

As an example, for the above input the transaction size is 10.

Therefore, setting ` -l 10` will result in an encrypted result of `10`, but `-l 1` will result in an encrypted result of `0`.

# Running The Client
`cd privacy_in_pcn/client/src/client` run `flask run` on Windows or `sudo FLASK_APP=app.py flask run --port=80 --host=0.0.0.0` on Linux to run the application.

There available REST methods are:
* `/register` - send a POST with a dictionary of `{clientName: ip}` so the client will know where to send message to this name.
* `/get-name` - send a GET to retrieve the client's name (hex).
* `/get-messages` - send a GET to retrieve the client's messages (that was directed to him).
* `/be-alice/<amount>/<route>` - send a GET to initiate a payment of `amount` from the current client through the route.
* `/onion` - send a POST message with an onion-routing message. The client will process that message and continue with the onion protocol.
* `/backward` - send a POST message with Bob's secret. 
* `/bulk' - to do the above operations in batches

# Rerun the Evaluation
Run `python manage_tests.py`:
this file should prepare the full cloud environment, assuming that you have an authenticated Azure account with permissions (and quota) to create 8 `Standard_DC1s_v2` VMs in `northeurope` and `eastus`.

It runs the experiment that is showen in the paper: evaluate the throughput and latency of 1-4 relays and 0-1000 issued payments/sec.