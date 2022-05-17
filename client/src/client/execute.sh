#!/bin/bash

cd /home/azureuser/privacy_in_pcn/client/src/ || exit 1
sudo python3 -m pip install python-rapidjson starlette uvicorn==0.14.0 pycryptodome
sudo uvicorn app:app --port 80 --host 0.0.0.0

