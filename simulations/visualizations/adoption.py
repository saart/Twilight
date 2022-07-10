import json
import os
import numpy.random
from typing import List, Set

import lightning
from lightning.classes import Node
from lightning.utils import load_list_from_disk


from matplotlib import pylab, pyplot
import seaborn
seaborn.set()
pylab.rcParams.update({
    'figure.dpi': 100,
    'figure.titlesize': 14,
    'axes.labelsize': 24,
    'xtick.labelsize': 18,
    'ytick.labelsize': 18,
    'lines.linewidth': 2,
    'legend.fontsize': 15,
    'pdf.fonttype': 42,
})


DATA_FILE = os.path.dirname(lightning.__file__) + '/../../../../describegraph_nov_21.json'


def _has_private_route(nodes, update_component, degree):
    pairs_count = lambda n: n * (n-1) / 2
    nodes = sorted(nodes, key=degree, reverse=True)
    nodes_in_component = set()
    data = []
    for node in nodes:
        nodes_in_component.add(node)
        to_update, should_append = update_component(node)
        nodes_in_component.update(to_update)
        if should_append:
            data.append(pairs_count(len(nodes_in_component)) / pairs_count(len(nodes)))
    return data


def has_private_route():
    nodes: List[Node] = load_list_from_disk(path=DATA_FILE)
    nodes_data = _has_private_route(nodes, lambda n: ([c.other_node(n) for c in n.channels], True), lambda n: len(n.channels))

    channels_json = json.load(open(DATA_FILE, 'rb'))
    lnbig_nodes = [n for n in channels_json["nodes"] if "lnbig" in n["alias"].lower()]
    lnbig_node_set = set(n["pub_key"] for n in lnbig_nodes)
    lnbig_node_set = {n for n in nodes if n.name in lnbig_node_set}
    bitfinx_nodes = [n for n in channels_json["nodes"] if n["pub_key"] in ["03cde60a6323f7122d5178255766e38114b4722ede08f7c9e0c5df9b912cc201d6", "033d8656219478701227199cbd6f670335c8d408a92ae88b962c49d4dc0e83e025"]]
    lnbig_in = False

    def update_companies(node):
        nonlocal lnbig_in
        if node in lnbig_node_set:
            to_update = [c.other_node(n) for n in lnbig_node_set for c in n.channels]
            to_update.extend(lnbig_node_set)
            should_add = not lnbig_in
            lnbig_in = True
            return to_update, should_add
        else:
            return [c.other_node(node) for c in node.channels], True

    def degree_company(node):
        if node in lnbig_node_set:
            return len({c.other_node(n) for n in lnbig_node_set for c in n.channels}) + 10000  # give bias to lnbig
        return len(node.channels)

    companies_data = _has_private_route(nodes, update_companies, degree_company)
    print(companies_data[:20])
    return nodes_data, companies_data


def has_private_route_random_adoption():
    nodes: List[Node] = load_list_from_disk(path=DATA_FILE)
    pairs_count = lambda n: n * (n - 1) / 2
    total_pairs = pairs_count(len(nodes))
    data = []

    relevant_nodes = [n for n in nodes if len(n.channels) > 1]
    for _ in range(100):
        data.append([])
        components: List[Set[Node]] = []
        adoption_order = numpy.random.permutation(relevant_nodes)
        for node in adoption_order:
            new_big_component = {c.other_node(node) for c in node.channels}.union([node])
            components_to_merge = [c for c in components if c.intersection(new_big_component)]
            for component in components_to_merge:
                new_big_component.update(component)
            components = [c for c in components if c not in components_to_merge] + [new_big_component]
            data[-1].append(sum(pairs_count(len(c)) for c in components) / total_pairs)
    return data


def plot_adoption():
    nodes_data, companies_data = has_private_route()
    random_data = has_private_route_random_adoption()
    fig, ax = pyplot.subplots()
    ax.plot(list(range(1, len(companies_data) + 1)), companies_data, label="Organizations by degree")
    ax.plot(list(range(1, len(nodes_data) + 1)), nodes_data, label="Relays by degree")
    number_of_nodes = len(random_data[-1])
    random_data_by_nodes = [[l[i] for l in random_data] for i in range(number_of_nodes)]
    ax.plot(list(range(1, number_of_nodes + 1)),
                [numpy.average(l) for l in random_data_by_nodes], label="Uniform adoption")
    ax.fill_between(list(range(1, number_of_nodes + 1)),
                   [numpy.average(l) - numpy.std(l) for l in random_data_by_nodes],
                   [numpy.average(l) + numpy.std(l) for l in random_data_by_nodes], alpha=0.2, color="green")
    pyplot.yticks([0, 0.2, 0.4, 0.6, 0.8, 1], ["0", "20%", "40%", "60%", "80%", "100%"])
    pyplot.xscale('log')
    pyplot.ylim((0, 1.1))
    pyplot.xticks(list(range(1, 11, 1)) + list(range(20, 101, 10)) + list(range(200, 1001, 100)) + list(range(2000, 5001, 1000)))
    pyplot.xlabel('# Adopters (log scale)')
    pyplot.ylabel("Private Paths")
    pyplot.legend(loc=(-0.01, 0.74))
    pyplot.tight_layout()
    fig.savefig(r'C:\Users\user\Downloads\privacy_by_adopters.pdf', format='pdf')
    pyplot.show()


if __name__ == '__main__':
    # has_private_route()
    # has_private_route_random_adoption()
    plot_adoption()
