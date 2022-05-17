import hashlib
import os
import re
import json

import pytest
import subprocess
import web3.contract
from ecpy.curves import Point
from ecpy.keys import ECPrivateKey

from client.relay import Client
from client.utils import DEFAULT_CURVE

w3 = web3.Web3(web3.HTTPProvider("http://127.0.0.1:7545"))
ETH = 10 ** 18

SOLCJS = "C:\\Users\\user\\AppData\\Roaming\\npm\\solcjs.cmd"
CACHE_INDICATOR = "..\\cache.bin"


def get_balance(contract_address: str) -> float:
    return w3.eth.getBalance(contract_address)


@pytest.fixture(scope="session", autouse=True)
def compile_contract():
    channel_data = hashlib.md5(open("..\\channel.sol").read().encode()).digest()
    previous_data = open(CACHE_INDICATOR, 'rb').read() if os.path.exists(CACHE_INDICATOR) else None
    if not os.path.exists("..\\channel_sol_EllipticCurve.abi") or channel_data != previous_data:
        subprocess.check_output([SOLCJS, "channel.sol", "--abi", "--bin", "--overwrite"], cwd='..')
        open(CACHE_INDICATOR, 'wb').write(channel_data)


@pytest.fixture(scope="session")
def alice():
    return w3.eth.accounts[1]


@pytest.fixture(scope="session")
def bob():
    c = Client()
    c.init_blockchain_keys()
    pub = c.bc_private_key.get_public_key().W
    return w3.solidityKeccak(["uint256", "uint256"], [pub.x, pub.y])[:20]


@pytest.fixture
def client():
    client = Client()
    client.init_blockchain_keys()
    return client


@pytest.fixture(scope="session")
def contract(alice, bob):
    library_abi = json.load(open("..\\channel_sol_EllipticCurve.abi"))
    library_compiled_sol = open("..\\channel_sol_EllipticCurve.bin").read()
    test_contract = w3.eth.contract(abi=library_abi, bytecode=library_compiled_sol)
    tx_hash = test_contract.constructor().transact({'from': w3.eth.accounts[0], 'value': 1 * ETH})
    tx_receipt = w3.eth.waitForTransactionReceipt(tx_hash)

    abi = json.load(open("..\\channel_sol_PrivChannel.abi"))
    compiled_sol = open("..\\channel_sol_PrivChannel.bin").read()
    compiled_sol = re.sub(r"__\$[0-9a-f]+\$__", tx_receipt.contractAddress[2:], compiled_sol)
    test_contract = w3.eth.contract(abi=abi, bytecode=compiled_sol)
    tx_hash = test_contract.constructor(bob).transact({'from': alice, 'value': 1 * ETH})
    tx_receipt = w3.eth.waitForTransactionReceipt(tx_hash)
    assert tx_receipt['status']
    contract = w3.eth.contract(
        address=tx_receipt.contractAddress,
        abi=abi,
    )
    return contract


def test_happy_flow_decrypt_enclave(contract):
    result = contract.functions.decryptEnclaveByKey(b'\x01' * 32, b'\x02'*32).call()
    assert result == b'\x03' * 32


def test_sad_flow_verify_relay_signature(contract):
    with pytest.raises(web3.exceptions.ContractLogicError) as e:
        contract.functions.verifyRelaySignature(b'\x00' * 32, 3, 4, 5, 6).call()
    assert "Input Failure: Signature verification failure." in e.value.args[0]


def test_happy_flow_verify_relay_signature(contract, client):
    hashed = w3.solidityKeccak(["bytes32"], [b'\x01' * 32])
    result = client.sign_to_blockchain(hashed)
    pubkey = client.bc_private_key.get_public_key().W
    contract.functions.verifyRelaySignature(b'\x01' * 32, result[0], result[1], pubkey.x, pubkey.y).call()
    # no exception


def test_find_shared_key(contract):
    secret = 5
    expected = w3.solidityKeccak(["uint256"], [secret])

    assert contract.functions.findSharedKey(secret).call() == expected


@pytest.mark.parametrize("input_arr, expected", [
    (b'\x01' * 20, False),
    (b'\x00' * 20, True),
    (b'\x01' * 4 + b'\x00' * 16, True),
    (b'\x01' * 4 + b'\x00' * 16 + b'\x01', True),  # the 21'th bytes is not zero
    (b'\x00' * 19 + b'\x01', False),
])
def test_is_valid_enclave_output(contract, input_arr, expected):
    assert contract.functions.isValidEnclaveOutput(input_arr).call() is expected


@pytest.mark.parametrize("input_arr, expected", [
    (b'\x00' * 20, 0),
    (int(5).to_bytes(4, 'little'), 5),
    (int(10000).to_bytes(4, 'little'), 10000),
])
def test_enclave_output_to_transaction_size(contract, input_arr, expected):
    input_arr += b'\x00' * (20-len(input_arr))
    assert contract.functions.enclaveOutputToTransactionSize(input_arr).call() == expected


def test_get_commitment_happy_flow(contract, client, alice):
    transaction_size = 5
    relay_secret = 123
    relay_dh_pubkey = ECPrivateKey(relay_secret, curve=DEFAULT_CURVE).get_public_key().W
    bob_secret = 456

    shared_point = DEFAULT_CURVE.mul_point(bob_secret, Point(relay_dh_pubkey.x, relay_dh_pubkey.y, curve=DEFAULT_CURVE))
    shared_secret = w3.solidityKeccak(["uint256"], [shared_point.x])
    enclave_decrypted_output = [transaction_size] + [0] * 19
    enclave_encrypted_output = bytes([a ^ b for a, b in zip(enclave_decrypted_output, shared_secret)])

    hashed = w3.solidityKeccak(["bytes32"], [enclave_encrypted_output + b'\x00' * 12])
    relay_signature_x, relay_signature_y = client.sign_to_blockchain(hashed)
    relay_pubkey = client.bc_private_key.get_public_key().W

    args = enclave_encrypted_output, relay_signature_x, relay_signature_y, relay_pubkey.x, relay_pubkey.y, shared_point.x
    assert contract.functions.get_commitment(*args).call({'from': alice}) == transaction_size

