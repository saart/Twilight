import time

from subprocess import check_output

BATCH_SIZE = 50

start = time.time()
cmd = "./app -h 39ac9ae97b232b7c024f02b0f9c3e71977c4fe97727484ddd047a5d22b6c1a8164ff83d0c4a02aa1728f36186fec8c05d6fe4beaf5a02415cbd063d1cb0a23a9 -c 1BF4ED8F378ED3D8885CA71808D785BC274E5C0A -l 100 -k 04A6E218A52D79346D4E295056BC7DAAD6A8A25E"
counter = 0
for i in range(2):
    out = check_output(' && '.join(cmd for _ in range(BATCH_SIZE)), shell=True)
    counter += out.count(b"Enclave failed due to prev liquidity")
    print("Counter:", counter / ((i+1) * BATCH_SIZE), '\r', end='', flush=True)
print()
print("Total seconds", round(time.time() - start))
