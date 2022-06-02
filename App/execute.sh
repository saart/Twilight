#!/bin/bash

cd /home/azureuser/privacy_in_pcn/
export LD_LIBRARY_PATH=/opt/intel/sgxsdk/sdk_libs/:/home/azureuser/pistache/prefix/lib/x86_64-linux-gnu/ && ./app
