import functools

import os
import time
from collections import defaultdict
from typing import Optional, Tuple, Dict, List
import struct
import random

from ecpy.keys import ECPublicKey, ECPrivateKey
from ecpy.ecdsa import ECDSA

from client.channel_state import ChannelState, PendingPayment
from client.lib.chacha20 import chacha20_encrypt
from client import utils
from client.logger import CLIENT_NAME_SIZE, CLIENT_NAME, logger, timing_log
from client.utils import TRANSACTION_SIZE, CURVE_PUBLIC_KEY_SIZE, CURVE_PRIVATE_KEY_SIZE, secret_to_pubkey_output, \
    simulate_transaction_encryption, DEFAULT_CURVE, find_shared_secret, build_onion_route, ONION_SIZE, ONION_ROUTE_SIZE

EMPTY_CLIENT_NAME = b'.' * CLIENT_NAME_SIZE
DEFAULT_PRIVATE = 4686042

FORWARD_MESSAGE_FORMAT = (
        f'{TRANSACTION_SIZE}s'  # previous_enclave_output
        + f'{TRANSACTION_SIZE}s'  # previous_enclave_encrypted_key
        + f'{CURVE_PUBLIC_KEY_SIZE}s'  # secret_pubkey
)
FORWARD_MESSAGE_SIZE = struct.calcsize(FORWARD_MESSAGE_FORMAT)
BACKWARD_MESSAGE_FORMAT = (
        f'{CURVE_PUBLIC_KEY_SIZE}s'  # secret_pubkey
        + f'{CURVE_PRIVATE_KEY_SIZE}s'  # secret
)
BACK_MESSAGE_SIZE = struct.calcsize(BACKWARD_MESSAGE_FORMAT)

# This key is generated in the channel's initialization phase
ENCLAVE_SECRET = [21, 82, 15, 151, 146, 163, 170, 236, 229, 18, 142, 72, 94, 107, 248, 22, 241, 230, 254, 84]

MAX_PENDING_PAYMENTS = 3_000


class PaymentDeclined(Exception):
    pass


class ForwardMessage:
    def __init__(self, previous_enclave_output: bytes, previous_enclave_encrypted_key: bytes, secret_pubkey: bytes,
                 rest_onion_route: bytes, source_name: bytes):
        assert len(previous_enclave_output) == TRANSACTION_SIZE, "Wrong size: previous_enclave_output"
        assert len(
            previous_enclave_encrypted_key) == TRANSACTION_SIZE, "Wrong size: previous_enclave_encrypted_key"
        assert len(secret_pubkey) == CURVE_PUBLIC_KEY_SIZE, "Wrong size: secret_pubkey"
        assert len(rest_onion_route) == ONION_ROUTE_SIZE, "Wrong size: rest_onion_route"
        self.previous_enclave_output: bytes = previous_enclave_output
        self.previous_enclave_encrypted_key: bytes = previous_enclave_encrypted_key
        self.secret_pubkey: bytes = secret_pubkey
        self.rest_onion_route: bytes = rest_onion_route
        self.source_name: bytes = source_name

    @staticmethod
    def parse(data: bytes, rest_onion_route: bytes, source_name: bytes) -> "ForwardMessage":
        try:
            return ForwardMessage(*struct.unpack(FORWARD_MESSAGE_FORMAT, data), rest_onion_route=rest_onion_route,
                                  source_name=source_name)
        except Exception:
            logger.error(f"Could not parse message {data}", exc_info=True)
            raise

    def dump(self) -> bytes:
        return struct.pack(
            FORWARD_MESSAGE_FORMAT, self.previous_enclave_output, self.previous_enclave_encrypted_key,
            self.secret_pubkey
        )


class BackwardMessage:
    def __init__(self, secret_pubkey: bytes, secret: bytes):
        assert len(secret_pubkey) == CURVE_PUBLIC_KEY_SIZE, "Wrong size: secret_pubkey"
        assert len(secret) == CURVE_PRIVATE_KEY_SIZE, "Wrong size: secret"
        self.secret_pubkey: bytes = secret_pubkey
        self.secret: bytes = secret

    @staticmethod
    def parse(data: bytes) -> "BackwardMessage":
        return BackwardMessage(*struct.unpack(BACKWARD_MESSAGE_FORMAT, data))

    def dump(self) -> bytes:
        return struct.pack(BACKWARD_MESSAGE_FORMAT, self.secret_pubkey, self.secret)


class Client:
    KNOWN_CLIENTS: Dict[bytes, "Client"] = {}  # For unit tests

    def __init__(self, name: Optional[bytes] = None):
        self.name: bytes = name or CLIENT_NAME
        self.curve = DEFAULT_CURVE
        self.bc_private_key = None
        self.input_messages: List[Tuple[float, ForwardMessage]] = []
        self.channel_states: Dict[bytes, ChannelState] = defaultdict(ChannelState)
        self.pub_to_secret: Dict[bytes, bytes] = {}
        self.pub_to_times: Dict[bytes, List[Optional[float]]] = {}
        Client.KNOWN_CLIENTS[self.name] = self

    @functools.lru_cache(maxsize=50)
    def get_onion_key(self, other_name: bytes) -> bytes:
        return b'|'.join(sorted([self.name, other_name]))  # This key is generated in the channel's initialization phase

    def init_blockchain_keys(self, private: int = DEFAULT_PRIVATE):
        self.bc_private_key = ECPrivateKey(private, curve=self.curve)

    def sign_to_blockchain(self, message: bytes) -> Tuple[int, int]:
        return ECDSA(fmt="ITUPLE").sign(message, self.bc_private_key)

    def verify_to_blockchain(self, message: bytes, signature: Tuple[int, int],
                             public_key: Optional[ECPublicKey] = None) -> bool:
        try:
            public_key = public_key or self.bc_private_key.get_public_key()
            return ECDSA(fmt="ITUPLE").verify(message, signature, public_key)
        except:
            return False

    def load_forward_message(self, encrypted_message: bytes) -> ForwardMessage:
        start = time.time()
        # extract key
        source_name = encrypted_message[:CLIENT_NAME_SIZE]
        encrypted_message = encrypted_message[CLIENT_NAME_SIZE:]
        key = self.get_onion_key(source_name)

        # compute data
        data = chacha20_encrypt(encrypted_message[:FORWARD_MESSAGE_SIZE], key)
        rest_onion_route = chacha20_encrypt(encrypted_message[FORWARD_MESSAGE_SIZE:], self.name)
        result = ForwardMessage.parse(data, rest_onion_route, source_name)
        timing_log('onion - load_forward_message', time.time() - start)
        return result

    def send_message(self, target_name: bytes, message) -> bytes:
        start = time.time()
        data = message.dump()
        key = self.get_onion_key(target_name)
        result = self.name + chacha20_encrypt(data, key) + message.rest_onion_route
        timing_log('onion - send_message', time.time() - start)
        return result

    def create_next_forward_message(self, message: ForwardMessage) -> ForwardMessage:
        next_onion_route = message.rest_onion_route[ONION_SIZE:] + os.urandom(ONION_SIZE)
        if len(self.channel_states[message.source_name].pending_payments) > MAX_PENDING_PAYMENTS:
            raise PaymentDeclined()
        enclave = utils.trigger_enclave(secret_pubkey=message.secret_pubkey,
                                        encrypted_given_amount=message.previous_enclave_output,
                                        encrypted_key=message.previous_enclave_encrypted_key,
                                        state=self.channel_states[message.source_name])
        self.channel_states[message.source_name].add_pending_payment(message.secret_pubkey, message.source_name,
                                                                     enclave)
        return ForwardMessage(
            previous_enclave_output=enclave.encrypted_out_amount,
            previous_enclave_encrypted_key=enclave.key_for_next,
            secret_pubkey=message.secret_pubkey,
            rest_onion_route=next_onion_route,
            source_name=self.name
        )

    def create_next_backward_message(self, message: BackwardMessage) -> Tuple[bytes, Optional[BackwardMessage]]:
        secret = int.from_bytes(message.secret, 'little')
        for state in self.channel_states.values():
            next_client = state.resolve(message.secret_pubkey, secret)
            if next_client:
                # logger.debug(f"Backwarding message to {next_client.hex()}")
                return next_client, BackwardMessage(
                    secret=message.secret,
                    secret_pubkey=message.secret_pubkey,
                )
        # We're back to Alice
        if message.secret_pubkey not in self.pub_to_times:
            logger.error("Backwarded message reached the wrong Alice")
            return b"", None
        # logger.debug("Backwarded message reached Alice")
        self.pub_to_times[message.secret_pubkey][1] = time.time()
        return b"", None

    def process_forward_message(self, raw_message: bytes) -> Tuple[bytes, bytes, bool]:
        input_message: ForwardMessage = self.load_forward_message(raw_message)
        next_client_name = input_message.rest_onion_route[:ONION_SIZE]
        if next_client_name == EMPTY_CLIENT_NAME:
            return (*self.be_bob(input_message), True)
        try:
            start = time.time()
            output_message = self.create_next_forward_message(input_message)
            timing_log('onion - create next message', time.time() - start)
        except PaymentDeclined:
            logger.error("Message declined due to high concurrent payments")
            return b"", b"", False
        return next_client_name, self.send_message(next_client_name, output_message), False

    def process_backward_message(self, raw_message: bytes) -> Tuple[bytes, bytes]:
        input_message: BackwardMessage = BackwardMessage.parse(raw_message)
        next_client_name, output_message = self.create_next_backward_message(input_message)
        return next_client_name, output_message.dump() if output_message else b""

    def be_alice(self, route_clients: List[bytes], secret_pubkey: bytes) -> Tuple[bytes, bytes]:
        route = build_onion_route(tuple(route_clients))

        sim_enclave_private = 123
        start = time.time()
        shared_secret = find_shared_secret(sim_enclave_private, secret_pubkey)[::-1][:TRANSACTION_SIZE]
        previous_enclave_encrypted_key = bytes([a ^ b for a, b in zip(shared_secret, ENCLAVE_SECRET)])
        previous_enclave_output = simulate_transaction_encryption(shared_secret, 10)
        timing_log('alice_build_message', time.time() - start)

        message = ForwardMessage(
            previous_enclave_output=previous_enclave_output,
            previous_enclave_encrypted_key=previous_enclave_encrypted_key,
            secret_pubkey=secret_pubkey,
            rest_onion_route=route,
            source_name=self.name
        )

        self.pub_to_times[secret_pubkey] = [time.time(), None]
        return route_clients[0], self.send_message(route_clients[0], message)

    def be_bob(self, message: ForwardMessage) -> Tuple[bytes, bytes]:
        self.input_messages.append((time.time(), message))
        back_message = BackwardMessage(
            secret=self.pub_to_secret[message.secret_pubkey],
            secret_pubkey=message.secret_pubkey,
        )
        return message.source_name, back_message.dump()

    def ask_for_payment(self, private: Optional[int] = None) -> bytes:
        private = private or random.randint(1, 9999999)
        start = time.time()
        public = secret_to_pubkey_output(private)
        timing_log('bob_ask_for_payment', time.time() - start)
        self.pub_to_secret[public] = int.to_bytes(private, CURVE_PRIVATE_KEY_SIZE, 'little')
        return public

    def get_pending_payments(self, name: Optional[bytes] = None) -> List[PendingPayment]:
        if name:
            return list(self.channel_states[name].pending_payments.values())
        return sum([list(s.pending_payments.values()) for s in self.channel_states.values()], [])
