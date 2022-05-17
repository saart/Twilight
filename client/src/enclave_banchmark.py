import time
import random

import numpy

from client.channel_state import ChannelState
from client.utils import trigger_enclave, EnclaveOutput
from client.logger import logger

logger.setLevel("ERROR")
PUBKEY = bytes.fromhex("39ac9ae97b232b7c024f02b0f9c3e71977c4fe97727484ddd047a5d22b6c1a8164ff83d0c4a02aa1728f36186fec8c05d6fe4beaf5a02415cbd063d1cb0a23a9")
OUTPUT = bytes.fromhex("1BF4ED8F378ED3D8885CA71808D785BC274E5C0A")
ENCRYPTED_KEY = bytes.fromhex("04A6E218A52D79346D4E295056BC7DAAD6A8A25E")
ENCLAVE_OUTPUT = EnclaveOutput(OUTPUT, ENCRYPTED_KEY, PUBKEY)

BULK_COUNT = 100
STEP = 50


def calc_concurrent_data(max_pendings=10):
    to_return = {}
    state = ChannelState()
    for pending in range(0, max_pendings + 1, STEP):
        current_times = []
        for i in range(30):
            s = time.time()
            for i in range(BULK_COUNT):
                trigger_enclave(secret_pubkey=PUBKEY, encrypted_given_amount=OUTPUT, encrypted_key=ENCRYPTED_KEY, state=state)
            current_times.append(((time.time() - s) / BULK_COUNT) * 1000)
        to_return[pending] = (numpy.average(current_times), numpy.std(current_times))
        for _ in range(STEP):
            state.add_pending_payment(random.randint(0, 9999999999).to_bytes(10, 'little'), b'source', ENCLAVE_OUTPUT)
        print('.', end='', flush=True)
    print()
    return to_return


if __name__ == "__main__":
    print(calc_concurrent_data(max_pendings=1500))
