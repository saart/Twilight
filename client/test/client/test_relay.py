import pytest

from client import utils
from client.channel_state import ChannelState
from client.relay import Client, ForwardMessage, ONION_SIZE, ONION_ROUTE_SIZE
from client.lib.chacha20 import chacha20_encrypt
from client.utils import EnclaveOutput, TRANSACTION_SIZE, CURVE_PUBLIC_KEY_SIZE


@pytest.fixture
def client():
    c = Client()
    c.init_blockchain_keys()
    return c


@pytest.fixture
def message(client):
    return ForwardMessage(b"output".ljust(TRANSACTION_SIZE, b'.'),
                          b"prev_enc_key".ljust(TRANSACTION_SIZE, b'.'),
                          b"secret_pubkey".ljust(CURVE_PUBLIC_KEY_SIZE, b'.'),
                          b"rest_onion_route".ljust(ONION_ROUTE_SIZE, b'.'), client)


def test_sign_verify_happy_flow(client):
    message = b"123"
    signature = client.sign_to_blockchain(message)
    assert client.verify_to_blockchain(message, signature) is True


def test_sign_verify_sad_flow(client):
    message = b"123"
    signature = client.sign_to_blockchain(message)
    assert client.verify_to_blockchain(b"other", signature) is False
    assert client.verify_to_blockchain(message, b"other") is False
    assert client.verify_to_blockchain(message, client.sign_to_blockchain(b"other")) is False


def test_message_dump(client, message):
    network_data = message.dump()
    assert isinstance(network_data, bytes)
    m2 = ForwardMessage.parse(network_data, b'rest_onion'.ljust(ONION_ROUTE_SIZE, b'.'), client)
    assert m2.previous_enclave_output == message.previous_enclave_output
    assert m2.previous_enclave_encrypted_key == message.previous_enclave_encrypted_key
    assert m2.secret_pubkey == message.secret_pubkey
    assert m2.rest_onion_route.startswith(b'rest_onion')


def test_send_receive_message(client, message):
    client2 = Client()
    network_data = client.send_message(client2.name, message)
    m2 = client2.load_forward_message(network_data)
    assert m2.previous_enclave_output == message.previous_enclave_output
    assert m2.previous_enclave_encrypted_key == message.previous_enclave_encrypted_key
    assert m2.secret_pubkey == message.secret_pubkey
    pealed_onion_route = chacha20_encrypt(message.rest_onion_route, client2.name)
    assert m2.rest_onion_route == pealed_onion_route


def test_create_next_message(client, message, monkeypatch):
    monkeypatch.setattr(utils, "trigger_enclave",
                        lambda **kwrags: EnclaveOutput(b"12".ljust(TRANSACTION_SIZE, b'.'),
                                                       b"34".ljust(TRANSACTION_SIZE, b'.'),
                                                       b"56".ljust(CURVE_PUBLIC_KEY_SIZE, b'.'),
                                                       b'state'))
    result = client.create_next_forward_message(message)
    assert result.previous_enclave_output.startswith(b"12")
    assert result.previous_enclave_encrypted_key.startswith(b"34")
    # note: in the happy flow case we ignore the EnclaveOutput.key_for_secret
    assert result.secret_pubkey == message.secret_pubkey
    assert result.rest_onion_route.startswith(message.rest_onion_route[ONION_SIZE:])
    assert len(result.rest_onion_route) == len(message.rest_onion_route)


def test_be_alice(monkeypatch):
    alice = Client(b"alice")
    r1 = Client(b"...r1")
    r2 = Client(b"...r2")
    bob = Client(b"..bob")
    key_for_secret = bob.ask_for_payment(private=123)

    def enclave_mock(secret_pubkey: bytes, encrypted_given_amount: bytes, encrypted_key: bytes, state: ChannelState):
        return EnclaveOutput(encrypted_given_amount, encrypted_key, key_for_secret, b'state')

    monkeypatch.setattr(utils, "trigger_enclave", enclave_mock)

    name, raw_message = alice.be_alice([r1.name, r2.name, bob.name], key_for_secret)
    assert list(alice.pub_to_times.values())[0][0]
    name, raw_message, is_bob = r1.process_forward_message(raw_message)
    assert name == b"...r2" and is_bob is False and r1.get_pending_payments(b"alice")
    name, raw_message, is_bob = r2.process_forward_message(raw_message)
    assert name == b"..bob" and is_bob is False and r2.get_pending_payments(b"...r1")
    name, raw_message, is_bob = bob.process_forward_message(raw_message)
    assert name == b"...r2" and is_bob is True and not bob.get_pending_payments()
    name, raw_message = r2.process_backward_message(raw_message)
    assert name == b"...r1" and not r2.get_pending_payments()
    name, raw_message = r1.process_backward_message(raw_message)
    assert name == b"alice" and not r1.get_pending_payments()
    name, raw_message = alice.process_backward_message(raw_message)
    assert not name and not raw_message
    assert list(alice.pub_to_times.values())[0][1]

    assert not alice.input_messages
    assert not r1.input_messages
    assert not r2.input_messages
    assert bob.input_messages
    assert alice.pub_to_times[key_for_secret][1] is not None
