import time
from multiprocessing import Queue, Process
import concurrent.futures

from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route

from client.logger import logger, timing_log
from app_logic import execute_process

try:
    import rapidjson as json
except ImportError:
    logger.error("Importing slow json")
    import json


async def register(request):
    data = await request.body()
    jobs_queue.put(["register", [data]])
    return PlainTextResponse('Done')


async def bulk(request):
    data = await request.body()
    start = time.time()
    requests_list = json.loads(data)
    for method, args in requests_list:
        put_in_queue_thread.submit(jobs_queue.put, [method, [bytes.fromhex(args)]])
    timing_log('bulk', time.time() - start)
    return PlainTextResponse('Bulked')


async def onion(request):
    data = await request.body()
    jobs_queue.put(["onion", [data]])
    return PlainTextResponse('Forwarded')


async def backward(request):
    data = await request.body()
    put_in_queue_thread.submit(jobs_queue.put, ["backward", [data]])
    return PlainTextResponse('Backwarded')


async def be_alice(request):
    data = await request.body()
    put_in_queue_thread.submit(jobs_queue.put, ["be_alice", [data]])
    return PlainTextResponse('Aliced')


def initiate_many_from_bob(request):
    route = request.path_params['route']
    count = request.path_params['count']
    jobs_queue.put(["initiate_many_from_bob", (route, count)])
    return PlainTextResponse(f"Bobed {count}")


def initiate_bob_throughput(request):
    route = request.path_params['route']
    count = request.path_params['count']
    jobs_queue.put(["initiate_bob_throughput", (route, count)])
    return PlainTextResponse(f"Bob initiated throughput")


def initiate_bob_throughput_dynamic(request):
    route = request.path_params['route']
    count1 = request.path_params['count1']
    count2 = request.path_params['count2']
    jobs_queue.put(["initiate_bob_throughput_dynamic", (route, count1, count2)])
    return PlainTextResponse(f"Bob initiated dynamic throughput")


def initiate_from_bob(request):
    route = request.path_params['route']
    jobs_queue.put(["initiate_from_bob", (route,)])
    return PlainTextResponse('Bobed')


def get_name(request):
    jobs_queue.put(["get_name", []])
    return PlainTextResponse(results_queue.get())


def get_messages(request):
    jobs_queue.put(["get_messages", []])
    return PlainTextResponse(results_queue.get())


def get_times(request):
    jobs_queue.put(["get_times", []])
    return PlainTextResponse(results_queue.get())


jobs_queue: Queue = Queue()
results_queue: Queue = Queue()
p = Process(target=execute_process, args=(jobs_queue, results_queue))
p.daemon = True
p.start()
put_in_queue_thread = concurrent.futures.ThreadPoolExecutor(max_workers=5)
app = Starlette(debug=True, routes=[
    Route('/register', register, methods=['POST']),
    Route('/bulk', bulk, methods=['POST']),
    Route('/onion', onion, methods=['POST']),
    Route('/backward', backward, methods=['POST']),
    Route('/be_alice', be_alice, methods=['POST']),
    Route('/be-bob-many/{route}/{count}', initiate_many_from_bob),
    Route('/initiate-bob-throughput/{route}/{count}', initiate_bob_throughput),
    Route('/initiate-bob-throughput/{route}/{count1}/{count2}', initiate_bob_throughput_dynamic),
    Route('/be-bob/{route}', initiate_from_bob),
    Route('/register', register),
    Route('/get-name', get_name),
    Route('/get-messages', get_messages),
    Route('/get-times', get_times),
])
