import random

import multiprocessing

import networkx
from lightning.classes import Node, Channel
from lightning.utils import load_list_from_disk, get_channels
from typing import List, Iterable, Optional, Set
try:
    import seaborn
    from matplotlib import pylab, pyplot
    seaborn.set()
    pylab.rcParams.update({
        'figure.figsize': (7, 3.5),
        'figure.titlesize': 14,
        'axes.labelsize': 20,
        'xtick.labelsize': 18,
        'ytick.labelsize': 18,
        'lines.linewidth': 2,
        'legend.fontsize': 16,
    })
except ImportError:
    seaborn, pylab, pyplot = None, None, None


ADOPTER_COUNT = 100
TX_SIZE = 1_000_000

_graph: Optional[networkx.Graph] = None


def get_graph(nodes: Iterable[Node] = None, channels: Iterable[Channel] = None) -> networkx.Graph:
    global _graph
    if _graph:
        return _graph
    print('building graph')
    nodes: Iterable[Node] = nodes or load_list_from_disk(path=r"C:\temp\routes\lngraph_2021_06_07__23_25.json")
    channels: Iterable[Channel] = channels or get_channels()
    graph = networkx.DiGraph()
    graph.add_nodes_from(map(lambda n: n.name, nodes))
    graph.add_edges_from(map(lambda c: (c.node1.name, c.node2.name), channels))

    components = networkx.algorithms.components.weakly_connected_components(graph)
    main_connected_component = max(components, key=len)
    connected_graph = networkx.Graph()
    connected_graph.add_nodes_from(main_connected_component)
    for channel in channels:
        if channel.node1.name in main_connected_component and channel.node2.name in main_connected_component:
            connected_graph.add_edge(channel.node1.name, channel.node2.name)
    _graph = connected_graph
    return connected_graph


def remove_path(graph: networkx.Graph, path: List[str]):
    removed_edges = []
    if not path:
        return None
    for i in range(len(path) - 1):
        s, d = path[i], path[i + 1]
        graph.remove_edge(s, d)
        removed_edges.append((s, d))
    return removed_edges


def process_k_disjoint_routes_specific_src_dst(max_k: int, src, dst) -> List[int]:
    graph = get_graph()
    route_exists: List[int] = [0] * max_k
    removed_edges = set()
    for route_index in range(max_k):
        try:
            path = networkx.algorithms.shortest_paths.shortest_path(graph, src, dst)
            route_exists[route_index] = 1
            new_removed_edges = remove_path(graph, path)
            if not new_removed_edges:
                break
            removed_edges.update(new_removed_edges)
        except networkx.exception.NetworkXNoPath:
            break
    [graph.add_edge(s, d) for s, d in removed_edges]
    if random.random() < 0.000001:
        print('.', end='', flush=True)
    return route_exists


def process_distinct_shortest_k_routes(graph: networkx.Graph, max_k: int):
    route_exist: List[int] = [0] * max_k
    non_users = [n for n in graph.nodes if graph.degree[n] > 1]
    nodes = ((max_k, source, dst) for source in non_users for dst in non_users if source != dst)

    with multiprocessing.Pool(processes=6) as pool:
        results = pool.starmap(process_k_disjoint_routes_specific_src_dst, nodes)
        for r in results:
            for i in range(max_k):
                route_exist[i] += r[i]
            if random.random() < 0.00001:
                print(route_exist)
        print('route_exist:', route_exist)

    print("Final:", route_exist)
    return route_exist


def process_distinct_shortest_k_routes_sync(graph: networkx.Graph, max_k: int):
    nodes = ((max_k, source, dst) for source in graph.nodes for dst in graph.nodes if source != dst)
    for t in nodes:
        print(process_k_disjoint_routes_specific_src_dst(*t))


def print_path_lengths():
    # data = process_distinct_shortest_k_routes(get_graph(), k)
    data = [31995992, 30974788, 16382256, 9944562, 6633200, 4594592]
    data = [a / data[0] for a in data]

    pyplot.plot(list(range(1, len(data) + 1)), data)

    pyplot.yticks([0, 0.25, 0.5, 0.75, 1], ["0", "25%", "50%", "75%", "100%"])
    pyplot.ylabel('Fraction of relay-pairs\n(CCDF)')
    pyplot.xlabel('Channel-disjoint routes')
    pyplot.tight_layout()
    pyplot.savefig(fr'C:\Users\user\Downloads\disjoint_routes.pdf', format='pdf')
    pyplot.show()


if __name__ == '__main__':
    k = 6
    print_path_lengths()
