from collections import defaultdict

import json
import random
import functools
from typing import Dict, Set, Tuple, List

import networkx
from matplotlib import pyplot

PATH = 'C:/temp/routes/lngraph_2021_06_07__23_25.json'


class Node:
    def __init__(self, name=None):
        self.name = name
        self.neighbors: Set[Node] = set()

    def __repr__(self):
        return f'Node{self.name}'


@functools.lru_cache(maxsize=1)
def load_lightning_nodes() -> Dict[str, Node]:
    channels_json = json.load(open(PATH, 'rb'))
    nodes = {}
    for channel in channels_json['edges']:
        node1 = channel['node1_pub']
        node2 = channel['node2_pub']
        if node1 not in nodes:
            nodes[node1] = Node(name=node1)
        if node2 not in nodes:
            nodes[node2] = Node(name=node2)
        nodes[node1].neighbors.add(nodes[node2])
        nodes[node2].neighbors.add(nodes[node1])
    return nodes


def load_lightning_graph() -> networkx.Graph:
    nodes = load_lightning_nodes()
    graph = networkx.Graph()
    graph.add_nodes_from(list(nodes))
    channels = set()
    for node in nodes.values():
        for neighbor in node.neighbors:
            if (node, neighbor) not in channels and (neighbor, node) not in channels:
                graph.add_edge(node.name, neighbor.name)
                channels.add((node, neighbor))
    return graph


def shrink_by_betweenness(number_of_nodes=20) -> Dict[int, Set[int]]:
    nodes = load_lightning_nodes()
    graph = load_lightning_graph()
    result = networkx.betweenness_centrality(graph, k=number_of_nodes*5, seed=0)
    best_values = sorted(result.values())[-number_of_nodes:]
    reduced_nodes: List[str] = [k for k, v in result.items() if v in best_values][:number_of_nodes]

    name_to_index: Dict[str, int] = {k: i for i, k in enumerate(reduced_nodes)}
    return {name_to_index[n]: {name_to_index[n.name] for n in nodes[n].neighbors if n.name in reduced_nodes} for n in reduced_nodes}


def choose_routes(number_of_nodes=20, number_of_routes=250, draw_graph=False) -> List[Tuple[int, int, int]]:
    nodes_to_neighbors = shrink_by_betweenness(number_of_nodes=number_of_nodes)
    nodes: Set[int] = set(nodes_to_neighbors)
    graph = networkx.Graph()
    graph.add_nodes_from(nodes)
    for node in nodes:
        graph.add_edges_from([(node, neighbor) for neighbor in nodes_to_neighbors[node]])

    random.seed(0)
    routes = set()
    alice_counter = defaultdict(int)
    relay_counter = defaultdict(int)
    bob_counter = defaultdict(int)
    for node in nodes:
        neighbors = nodes_to_neighbors[node]
        if len(neighbors) < 2:
            continue  # This node can not be relay
        alice = random.choices(list(neighbors), weights=[1/alice_counter.get(n, 0.5)**2 for n in neighbors], k=1)[0]
        bob = random.choices(list(neighbors.difference({alice})), weights=[1/bob_counter.get(n, 0.5)**2 for n in neighbors if n != alice], k=1)[0]
        alice_counter[alice] += 1
        relay_counter[node] += 1
        bob_counter[bob] += 1
        routes.add((alice, node, bob))

    for _ in range(number_of_routes - len(nodes)):
        alice = random.choice(list(nodes))
        bob = random.choice(list(nodes.difference({alice}).difference(nodes_to_neighbors[alice])))
        routes.add(tuple(networkx.shortest_path(graph, alice, bob)))

    print("Alices:", dict(alice_counter), f"({len(alice_counter)}/{number_of_nodes}, max: {max(alice_counter.values())})")
    print("Relays:", dict(relay_counter), f"({len(relay_counter)}/{number_of_nodes}, max: {max(relay_counter.values())})")
    print("Bobs:", dict(bob_counter), f"({len(bob_counter)}/{number_of_nodes}, max: {max(bob_counter.values())})")

    if draw_graph:
        print(f"Routes ({len(routes)} relays on {number_of_nodes} nodes):", routes)
        colors: Dict[Tuple[int, int], str] = {}
        for color_index, route in enumerate(routes):
            for i in range(len(route) - 1):
                colors[(route[i + 1], route[i])] = colors[(route[i], route[i + 1])] = \
                ['red', 'green', 'blue', 'yellow', 'orange', 'brown', 'pink', 'olive', 'salmon'][color_index % 9]

        networkx.draw(graph, with_labels=True, edge_color=[colors.get((e[0], e[1]), "grey") for e in graph.edges()])
        pyplot.show()

    return list(routes)


if __name__ == '__main__':
    random.seed(0)
    # choose_routes(number_of_nodes=6, draw_graph=True)

    for topology_size in range(6, 16):
        routes = choose_routes(number_of_nodes=topology_size)
