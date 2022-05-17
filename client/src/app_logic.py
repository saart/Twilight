try:
    import rapidjson as json
except ImportError:
    import json
import queue
import time
from collections import defaultdict
from multiprocessing import Queue
from multiprocessing.dummy import Pool
import concurrent.futures

import requests
from requests.adapters import HTTPAdapter
from typing import List, Tuple, Dict, Union, Optional

from client.parameters import BULK_SEND
from client.relay import Client
from client.logger import logger, timing_log

name_to_ip = {}  # know clients
client = Client()
thread_pool = Pool(200)  # note: these are threads and not processes
requests_session = requests.Session()
requests_session.mount('http://', HTTPAdapter(pool_connections=1000, pool_maxsize=1000, max_retries=10))
results_queue: Optional[Queue] = None
thread_pool_executor = concurrent.futures.ThreadPoolExecutor(max_workers=300)
bulk_sending_queue = queue.Queue()


def execute_process(jobs_queue: Queue, results_queue_: Queue):
    global client, results_queue
    client = Client()
    results_queue = results_queue_
    print("My name is", client.name.hex())
    if BULK_SEND:
        concurrent.futures.ThreadPoolExecutor().submit(sending_thread)
    while True:
        func_name, attrs = jobs_queue.get()
        try:
            eval(func_name)(*attrs)
        except Exception:
            logger.error(f"Error executing job: {func_name, attrs}", exc_info=True)


def _send(uri, data):
    try:
        start = time.time()
        requests_session.post(uri, data)
        timing_log('send', time.time() - start, {'data_length': len(data), 'uri': uri})
    except Exception:
        logger.error("Exception in _send", exc_info=True)


def sending_thread():
    while True:
        try:
            to_send: Dict[str, List[Tuple[str, str]]] = defaultdict(list)
            should_wait = True
            for _ in range(50):
                try:
                    url, t = bulk_sending_queue.get(block=False)
                    to_send[url].append(t)
                except queue.Empty:
                    break
            else:
                should_wait = False
            for url, data in to_send.items():
                if data:
                    thread_pool_executor.submit(_send, f"http://{url}/bulk", json.dumps(data).encode())
                    # logger.info(f"Bulk", extra={'bulk_size': len(data)})
            if should_wait:
                time.sleep(0.1)
        except Exception:
            logger.error("Exception in sending_thread", exc_info=True)


def send(url: str, data: bytes, route: str):
    start = time.time()
    try:
        if BULK_SEND:
            bulk_sending_queue.put((url, (route, data.hex())))
        else:
            thread_pool_executor.submit(_send, f"http://{url}/{route}", data)
    except Exception as e:
        logger.exception("requests.post" + str(e))
    timing_log('send (to queue)', time.time() - start)


def get_name():
    results_queue.put(client.name.hex())


def register(request_data: bytes):
    for name, ip in json.loads(request_data).items():
        name_to_ip[bytes.fromhex(name)] = ip


def onion(request_data: bytes):
    start = time.time()
    try:
        next_client, data, is_bob = client.process_forward_message(request_data)
    except Exception as e:
        logger.exception("client.process_forward_message: " + str(e), exc_info=True)
        return
    if not next_client:
        return
    if not next_client:
        return
    if is_bob:
        # logger.debug("Bob got the FORWARD message. Sends BACKWARD.")
        send(name_to_ip[next_client], data, route='backward')
        return
    if next_client not in name_to_ip:
        logger.error(f"client.process_forward_message: Unknown next client: {next_client}")
        return
    send(name_to_ip[next_client], data, route='onion')
    timing_log('onion', time.time() - start)


def backward(request_data: bytes):
    start = time.time()
    try:
        next_client, data = client.process_backward_message(request_data)
    except Exception as e:
        logger.exception("client.process_backward_message" + str(e))
        return
    if not next_client:
        return
    if next_client not in name_to_ip:
        logger.exception("client.process_forward_message: Unknown next client")
        return
    send(name_to_ip[next_client], data, route='backward')
    timing_log('backward', time.time() - start)


def be_alice(request_data: bytes):
    start = time.time()
    req = json.loads(request_data.decode())
    route = list(map(bytes.fromhex, req["route"].split(',')))
    try:
        next_client, data = client.be_alice(route, bytes.fromhex(req["secret_hex"]))
    except Exception as e:
        logger.exception("client.be_alice: " + str(e))
        return
    send(name_to_ip[next_client], data, route='onion')
    timing_log('alice_start', time.time() - start)


def initiate_many_from_bob(route, count):
    for _ in range(int(count)):
        try:
            initiate_from_bob(route)
        except Exception:
            logger.error("Error initiate from bob (throughput sending)", exc_info=True)
            return


def _bob_throughput(route: List[str], count1: int, count2: Optional[int] = None):
    """
    It takes 0.5ms to initiate a single payment. Thus, total cpu time is around count*0.5.
    So the total sleep time is 1 - count*0.5, and we should split it between the initiations
    """
    count2 = count2 if count2 is not None else count1
    for count in [count1] * 30 + [count2] * 300:
        if count == 1:
            initiate_from_bob(route)
            time.sleep(1)
            continue
        for _ in range(5):
            start = time.time()
            for _ in range(int(count/5)):
                try:
                    initiate_from_bob(route)
                except Exception:
                    logger.error("Error initiate from bob (throughput sending)", exc_info=True)
                    return
            end = time.time()
            time.sleep(0.2 - (end - start))
        # logger.debug("Bob sent the initiating messages")


def initiate_bob_throughput(route, count):
    concurrent.futures.ThreadPoolExecutor().submit(_bob_throughput, route, int(count))


def initiate_bob_throughput_dynamic(route, count1, count2):
    concurrent.futures.ThreadPoolExecutor().submit(_bob_throughput, route, int(count1), int(count2))


def initiate_from_bob(route):
    start = time.time()
    route = list(map(bytes.fromhex, route.split(',')))
    try:
        secret = client.ask_for_payment()
    except Exception as e:
        logger.exception("client.be_bob: " + str(e))
        return
    route_for_alice = ','.join([name.hex() for name in route[1:]])
    data = {"secret_hex": secret.hex(), "route": route_for_alice}
    send(name_to_ip[route[0]], json.dumps(data).encode(), route='be_alice')
    timing_log('bob_start', time.time() - start)


def get_messages():
    results_queue.put(json.dumps(
        {timestamp: (message.previous_enclave_output.hex(), message.previous_enclave_encrypted_key.hex())
         for timestamp, message in client.input_messages}))


def get_times():
    min_t = time.time() - 2
    max_t = time.time() - 1
    is_relevant = lambda t: t[1] and (min_t < t[1] < max_t)
    results_queue.put(json.dumps([(round(v[0], 2), round(v[1], 2)) for v in client.pub_to_times.values() if is_relevant(v)]))
