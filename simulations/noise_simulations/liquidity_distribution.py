import json
import multiprocessing.pool
import os
import time
from scipy.stats import norm
from typing import Tuple, List
from pathlib import Path

import numpy
from matplotlib import pyplot
from scipy import sparse


TREE_HEIGHT = 28
NOISE_SIGMA = 120
NOISE_MEAN = (NOISE_SIGMA * 10) / (TREE_HEIGHT ** 0.5)

NORMAL_MEAN = NOISE_MEAN * TREE_HEIGHT
LEFT_PROB = 0.5
RIGHT_PROB = 1 - LEFT_PROB


def get_probabilities_to_move(from_liquidity: int, max_liquidity: int, should_add_noise: bool = True) -> Tuple[float, float, float]:
    """
    Returns a tuple:
      * the probability to move left (reduce one from the liquidity)
      * the probability to stay in place
      * the probability to move right
    """
    if not should_add_noise:
        if from_liquidity == 0:
            return 0, LEFT_PROB, RIGHT_PROB
        elif from_liquidity == max_liquidity:
            return LEFT_PROB, RIGHT_PROB, 0
        else:
            return LEFT_PROB, 0, RIGHT_PROB
    else:
        # Allow the transfer w.p. P(from_liquidity - noise > 1) = P(from_liquidity - 1 > noise) = CDF(from_liquidity - 1)
        left = LEFT_PROB * norm.cdf(from_liquidity - 1, NORMAL_MEAN, NOISE_SIGMA)
        right = RIGHT_PROB * norm.cdf(max_liquidity - from_liquidity - 1, NORMAL_MEAN, NOISE_SIGMA)
        return left, 1 - left - right, right


def build_transition_matrix(max_liquidity: int, should_add_noise: bool) -> sparse.dok_matrix:
    transitions_matrix = sparse.dok_matrix((max_liquidity + 1, max_liquidity + 1))
    for from_liquidity in range(max_liquidity + 1):
        left, stay, right = get_probabilities_to_move(from_liquidity, max_liquidity, should_add_noise)
        if from_liquidity != 0:
            transitions_matrix[from_liquidity, from_liquidity - 1] = left
        transitions_matrix[from_liquidity, from_liquidity] = stay
        if from_liquidity != max_liquidity:
            transitions_matrix[from_liquidity, from_liquidity + 1] = right
    return transitions_matrix


def find_stationary_state(liquidity, should_add_noise) -> List[float]:
    max_liquidity = 2 * liquidity
    transitions_matrix = build_transition_matrix(max_liquidity, should_add_noise).T

    low_diag = numpy.array([0] + [transitions_matrix[l, l - 1] for l in range(1, max_liquidity + 1)])
    diag = numpy.array([transitions_matrix[l, l] for l in range(max_liquidity + 1)])
    high_diag = numpy.array([transitions_matrix[l, l + 1] for l in range(max_liquidity)] + [0])

    # start with the base state
    distribution = numpy.array([1 / (max_liquidity + 1) for _ in range(max_liquidity + 1)])

    start = time.time()
    low_dist = numpy.empty_like(distribution)
    high_dist = numpy.empty_like(distribution)

    for i in range(100_000_000):
        low_dist[1:] = distribution[:-1]
        high_dist[:-1] = distribution[1:]
        distribution = (low_diag * low_dist) + (diag * distribution) + (high_diag * high_dist)

        if i % 10_000_000 == 0:
            store_distribution(liquidity, list(distribution))

    print(f"Liquidity: {liquidity}, Took {round(time.time() - start, 4)} seconds")
    store_distribution(liquidity, list(distribution))

    return list(distribution)


def plot_dist(distribution: List[float]):
    fig, ax = pyplot.subplots()
    ax.plot(list(range(len(distribution))), distribution)
    ax.set_xlabel("Liquidity")
    ax.set_ylabel("Probability")
    pyplot.show()


def store_distribution(liquidity: int, distribution: List[float], sigma: int = NOISE_SIGMA):
    path = f'data/{sigma}/liquidity_dis_{liquidity}'
    Path(path).parent.mkdir(exist_ok=True, parents=True)
    json.dump(distribution, open(path, 'w'))


def load_distribution(liquidity: int, sigma: int = NOISE_SIGMA) -> List[float]:
    return json.load(open(f'data/{sigma}/liquidity_dis_{liquidity}', 'r'))


def find_multiprocess(liquidities):
    cpus = os.cpu_count()
    print(f"Multiprocess with {cpus} CPUs")
    with multiprocessing.pool.Pool(cpus) as pool:
        futures = [pool.apply_async(find_stationary_state, kwds={"liquidity": liquidity, "should_add_noise": True})
                   for liquidity in liquidities]
        [f.get() for f in futures]


def main():
    find_multiprocess(range(5_000, 20_001, 1000))
    # distribution = find_stationary_state(10_000, should_add_noise=True)
    # plot_dist(distribution)
    # plot_dist(load_distribution(8_000))


if __name__ == '__main__':
    main()
