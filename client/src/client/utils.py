import functools

import struct

import time
import urllib.request
import urllib.error
from typing import NamedTuple, List, Tuple
import threading

import subprocess
from ecpy.curves import Curve, Point, ECPyException
from ecpy.keys import ECPrivateKey

from client.parameters import SKIP_ENCLAVE
from client.lib.chacha20 import chacha20_encrypt
from client.logger import logger, timing_log, CLIENT_NAME_SIZE

WORKING_DIR = '/home/azureuser/privacy_in_pcn/'
TRANSACTION_SIZE = 20
CURVE_PRIVATE_KEY_SIZE = 32
CURVE_PUBLIC_KEY_SIZE = 2 * CURVE_PRIVATE_KEY_SIZE
DEFAULT_CURVE = Curve.get_curve('secp256r1')
ENCLAVE_OUT = "output:\n{out}\nkey_encrypted_for_next:\n{next}\nmy_dh_pub:\n{pub}\n"

ONION_MESSAGE_FORMAT = (
    f'{CLIENT_NAME_SIZE}s'  # next client name
)
ONION_SIZE = struct.calcsize(ONION_MESSAGE_FORMAT)
ONION_ROUTE_SIZE = CLIENT_NAME_SIZE * 20
STATE_SIZE = 16

enclave_semaphore = threading.Semaphore()


def secret_to_pubkey_output(enclave_secret: int, curve=None) -> bytes:
    curve = curve or DEFAULT_CURVE
    enclave_pubkey = ECPrivateKey(enclave_secret, curve=curve).get_public_key().W
    x = int.to_bytes(enclave_pubkey.x, CURVE_PRIVATE_KEY_SIZE, 'little')
    y = int.to_bytes(enclave_pubkey.y, CURVE_PRIVATE_KEY_SIZE, 'little')
    return x + y


def bytes_to_point(pubkey: bytes, curve=None) -> Point:
    curve = curve or DEFAULT_CURVE
    enclave_dh_pubkey_x = int.from_bytes(pubkey[:CURVE_PRIVATE_KEY_SIZE], 'little')
    enclave_dh_pubkey_y = int.from_bytes(pubkey[CURVE_PRIVATE_KEY_SIZE:], 'little')
    return Point(enclave_dh_pubkey_x, enclave_dh_pubkey_y, curve=curve)


def simulate_transaction_encryption(shared_secret: bytes, transaction_size: int) -> bytes:
    tx = int.to_bytes(transaction_size, TRANSACTION_SIZE, 'little')
    return bytes([a ^ b for a, b in zip(tx, shared_secret)])


def xor_by_ecdh(arr: bytes, secret: int, public: bytes, curve=None) -> bytes:
    shared_secret = find_shared_secret(secret, public, curve)
    return bytes([a ^ b for a, b in zip(arr, shared_secret)])


@functools.lru_cache()
def find_shared_secret(secret: int, public: bytes, curve=None):
    curve = curve or DEFAULT_CURVE
    try:
        shared_point = curve.mul_point(secret, bytes_to_point(public, curve))
    except ECPyException:
        logger.error(f"Failed to find shared secret. Public: {public.hex()}, private: {secret}", exc_info=True)
        raise
    back_ind = int.from_bytes(int.to_bytes(shared_point.x, CURVE_PRIVATE_KEY_SIZE, 'little'), 'big')
    from Crypto.Hash import keccak
    k = keccak.new(digest_bits=256, data=int.to_bytes(back_ind, 32, 'big'))
    return k.digest()


@functools.lru_cache(maxsize=10)
def build_onion_route(route_clients: Tuple[bytes]) -> bytes:
    route = b"." * (ONION_ROUTE_SIZE - (len(route_clients) - 1) * CLIENT_NAME_SIZE)
    for last in route_clients[1:][::-1]:
        assert len(last) == CLIENT_NAME_SIZE, "got name with malformed size"
        route = chacha20_encrypt(route, last)
        route = last + route
    route = chacha20_encrypt(route, route_clients[0])
    assert ONION_ROUTE_SIZE == len(route), "total route size is wrong"
    return route


class EnclaveOutput(NamedTuple):
    encrypted_out_amount: bytes
    key_for_next: bytes
    key_for_secret: bytes
    state: bytes


def _trigger_enclave(params: List[str], pendings: str, max_retries=5) -> str:
    retries = 0
    s = time.time()
    while True:
        if retries > max_retries:
            raise Exception("Max retries reached")
        retries += 1
        try:
            enclave_semaphore.acquire()
            result = urllib.request.urlopen(f"http://127.0.0.1:9080/?{'&'.join(params)}",
                                            data=pendings.encode() if pendings else None).read().decode()
            if result.count('\n') < 6:
                logger.error(f"Bad output from enclave: {result}", extra={"params": params, "pendings": pendings[:100]})
                raise ValueError(f"Bad output from enclave: {result}")
            if "00000000000000000000000000000000000000" in result:
                logger.error("Invalid input to enclave")
                raise ValueError("Invalid input to enclave")
            timing_log('enclave', time.time() - s)
            return result
        except urllib.error.HTTPError as err:
            logger.error(f"HTTPError: {err}, retrying", exc_info=True)
        except (urllib.error.URLError, ConnectionResetError) as err:
            if "Request Entity Too Large" in str(err):
                logger.error(f"Entity large. Data size: {len(pendings)}", exc_info=True)
                raise
            logger.error(f"URLError, ConnectionResetError: {err}, retrying ({retries})", exc_info=True)
            try:
                if retries >= 2:
                    subprocess.check_output("sudo systemctl restart pcn-enclave", shell=True)
                    time.sleep(1)
            except Exception:
                pass
        except Exception:
            raise
        finally:
            enclave_semaphore.release()


def trigger_enclave(secret_pubkey: bytes, encrypted_given_amount: bytes, encrypted_key: bytes, state: "ChannelState"):
    pendings = state.resolved_since_state
    params = [f"bob_dh_pub={secret_pubkey.hex()}", f"encrypted_given_ammount={encrypted_given_amount.hex()}",
              f"encrypted_key={encrypted_key.hex()}", f"prev_liquidity={state.liquidity}"]
    if state.current_state:
        params.append(f"prev_state={state.current_state.hex()}")
    # logger.debug(f"Running enclave with params: {params} and {len(state.pending_payments)} pending payments")
    # logger.info("pending payments", extra={'pending_payments': len(state.pending_payments), 'resolved_since_state': pendings.count('#')})
    if SKIP_ENCLAVE:
        logger.debug(f"Skipping enclave")
        output: str = ENCLAVE_OUT.format(out=encrypted_given_amount.hex(), next=encrypted_key.hex(), pub=secret_pubkey.hex())
    else:
        output: str = _trigger_enclave(params, pendings)
    out_str, out, key_str, key, dh_str, dh, state_str, state, _ = output.split('\n')
    # logger.debug(f"Got output from enclave: {output.decode()}")
    assert out_str == "output:" and key_str == "key_encrypted_for_next:" and dh_str == "my_dh_pub:" and state_str == "state:", f"malformed output from enclave: {output}"
    bytes_out = bytes.fromhex(out)
    bytes_key = bytes.fromhex(key)
    bytes_dh = bytes.fromhex(dh)
    bytes_state = bytes.fromhex(state)
    assert len(bytes_out) == len(bytes_key) == TRANSACTION_SIZE and len(
        bytes_dh) == CURVE_PUBLIC_KEY_SIZE and len(bytes_state) == STATE_SIZE, f"malformed output sizes from enclave: {output}"
    return EnclaveOutput(bytes_out, bytes_key, bytes_dh, bytes_state)
