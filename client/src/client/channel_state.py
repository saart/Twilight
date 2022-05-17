from typing import Optional, Dict, NamedTuple

from client.logger import logger
from client.parameters import SKIP_ENCLAVE
from client.utils import xor_by_ecdh, EnclaveOutput

PENDING_HTLCS_ENCLAVE_DELIMITER = '#'


class PendingPayment(NamedTuple):
    source: bytes
    encrypted_amount: bytes
    enclave_pubkey: bytes
    key_for_next: bytes

    @staticmethod
    def _is_valid_plain(plain: bytes) -> bool:
        for i in range(4, 20):
            if plain[i] != 0:
                logger.error(f"Invalid plain in resolve: {plain}")
                return False
        return True

    def resolve(self, bob_secret: int) -> Optional[int]:
        # logger.debug(f"Trying to resolve with: {self.encrypted_amount.hex()}, {bob_secret}, {self.enclave_pubkey.hex()}")
        plain = xor_by_ecdh(self.encrypted_amount, bob_secret, self.enclave_pubkey)
        return int.from_bytes(plain, 'little') if self._is_valid_plain(plain) else None

    def get_enclave_format(self, positive: bool) -> str:
        return f'{self.encrypted_amount.hex()}{self.key_for_next.hex()}{0 if positive else 1}'


class ChannelState:
    def __init__(self, capacity=100000):
        self.liquidity = capacity
        self.pending_payments: Dict[bytes, PendingPayment] = {}
        self.current_state: Optional[bytes] = None
        self.resolved_since_state: str = ''

    def add_pending_payment(self, payment_id: bytes, source: bytes, enclave_output: EnclaveOutput):
        payment = PendingPayment(
            source, enclave_output.encrypted_out_amount, enclave_output.key_for_secret, enclave_output.key_for_next
        )
        self.pending_payments[payment_id] = payment
        self.current_state = enclave_output.state
        self.resolved_since_state = ''

    def resolve(self, payment_id: bytes, bob_secret: int) -> Optional[bytes]:
        payment = self.pending_payments.get(payment_id)
        if payment:
            self._for_enclave_dirty = True
            self.resolved_since_state = PENDING_HTLCS_ENCLAVE_DELIMITER.join([self.resolved_since_state, payment.get_enclave_format(positive=False)])
            if SKIP_ENCLAVE:
                return self.pending_payments.pop(payment_id).source
            result = payment.resolve(bob_secret)
            if result is not None:
                self.liquidity += result
                return self.pending_payments.pop(payment_id).source
            else:
                logger.error(f"Could not resolve payment {payment_id} with {bob_secret}")
        return None

