import pytest

from client.channel_state import PendingPayment, ChannelState
from client.utils import secret_to_pubkey_output, simulate_transaction_encryption, DEFAULT_CURVE, EnclaveOutput, \
    find_shared_secret


@pytest.fixture
def curve():
    return DEFAULT_CURVE


def encrypt_transaction(curve, bob_secret: int, enclave_secret: int, transaction_size: int):
    shared_secret = find_shared_secret(bob_secret, secret_to_pubkey_output(enclave_secret), curve)
    return simulate_transaction_encryption(shared_secret, transaction_size)


def test_pending_payment_resolve(curve):
    transaction_size = 5
    bob_secret = 1234
    enclave_secret = 9999

    enclave_encrypted_output = encrypt_transaction(curve, bob_secret, enclave_secret, transaction_size)
    enclave_pubkey_bytes = secret_to_pubkey_output(enclave_secret, curve)

    payment = PendingPayment(b"source", enclave_encrypted_output, enclave_pubkey_bytes, b'123')
    assert payment.resolve(bob_secret) == 5


@pytest.mark.parametrize("pid, secret, expected, new_liquidity", [
    (b"1", 1111, b"source", 110),  # happy flow
    (b"1", 3333, None, 100),  # wrong secret
    (b"2", 1111, None, 100),  # wrong payment id
])
def test_channel_state_resolve(curve, pid, secret, expected, new_liquidity):
    state = ChannelState(capacity=100)
    enclave_encrypted_output = encrypt_transaction(curve, 1111, 2222, 10)
    enclave_pubkey_bytes = secret_to_pubkey_output(2222, curve)
    enclave_output = EnclaveOutput(enclave_encrypted_output, b"123", enclave_pubkey_bytes, b"state")
    state.add_pending_payment(b"1", b"source", enclave_output)
    assert state.resolve(pid, secret) == expected
    assert state.liquidity == new_liquidity
