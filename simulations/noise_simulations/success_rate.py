import multiprocessing.pool
from typing import List
import json

import numpy
import seaborn
from matplotlib import pylab, pyplot
seaborn.set()
pylab.rcParams.update({
    'figure.dpi': 100,
    'figure.titlesize': 14,
    'axes.labelsize': 24,
    'xtick.labelsize': 18,
    'ytick.labelsize': 18,
    'lines.linewidth': 2,
    'legend.fontsize': 17,
    'pdf.fonttype': 42,
})

REPETITIONS = 100_000_000
ALICE_TX_SIZE = 1


def load_distribution(liquidity: int, sigma: int = 120) -> List[float]:
    return json.load(open(f'data/{sigma}/liquidity_dis_{liquidity}', 'r'))


def compute_success_rate(liquidity: int, sigma: int, repetitions=REPETITIONS, with_noise: bool = True):
    if with_noise:
        distribution = load_distribution(liquidity, sigma)
        if numpy.isnan(distribution[0]):
            print("bad liquidity:", liquidity)
            if 12_000 <= liquidity < 14_000:
                return compute_success_rate(liquidity + 100, sigma, repetitions, with_noise)
            else:
                return compute_success_rate(liquidity + 500, sigma, repetitions, with_noise)
        liquidities = numpy.random.choice(list(range(len(distribution))), p=distribution, size=repetitions)
        noises = numpy.random.default_rng().normal((sigma * 10) * (28 ** 0.5), sigma, size=repetitions)
        payment_failed = liquidities - noises < ALICE_TX_SIZE
    else:
        liquidities = numpy.random.choice(list(range(2 * liquidity)), size=repetitions)
        payment_failed = liquidities < ALICE_TX_SIZE

    success_ratio = numpy.count_nonzero(payment_failed) / repetitions
    print(f"Success ratio of {liquidity} is {success_ratio}")
    return success_ratio


def multiprocess_compute_success_ratio(liquidities: List[int], sigma: int, with_noise: bool = True):
    with multiprocessing.pool.Pool(8) as pool:
        futures = {liquidity: pool.apply_async(compute_success_rate,
                                               kwds={"liquidity": liquidity, "sigma": sigma, "with_noise": with_noise})
                   for liquidity in liquidities}
        data = {liquidity: future.get() for liquidity, future in futures.items()}
    print("with_noise", with_noise, "sigma", sigma, "data", data)
    return data


def plot_success_ratio(liquidities: List[int]):
    liquidities.sort()
    # with_noise_100 = multiprocess_compute_success_ratio(liquidities, sigma=100, with_noise=True)
    # with_noise_138 = multiprocess_compute_success_ratio(liquidities, sigma=138, with_noise=True)
    # with_noise_211 = multiprocess_compute_success_ratio(liquidities, sigma=211, with_noise=True)
    # without_noise = multiprocess_compute_success_ratio(liquidities, sigma=0, with_noise=False)
    with_noise_100 = {6000: 0.00101035, 6500: 0.0005008, 7000: 0.00033847, 7500: 0.00025267, 8000: 0.00020188, 8500: 0.00016697, 9000: 0.00014135, 9500: 0.00012583, 10000: 0.00010935, 10500: 9.961e-05, 11000: 9.02e-05, 11500: 8.452e-05, 12000: 7.795e-05, 12500: 7.221e-05, 13000: 6.656e-05, 13500: 6.168e-05, 14000: 5.829e-05, 14500: 5.659e-05, 15000: 5.397e-05, 15500: 5.086e-05, 16000: 4.828e-05, 16500: 4.588e-05, 17000: 4.506e-05, 17500: 4.176e-05, 18000: 4.083e-05, 18500: 4.04e-05, 19000: 3.811e-05, 19500: 3.724e-05, 20000: 3.639e-05}
    with_noise_138 = {6000: 0.99999973, 6500: 0.9999998, 7000: 0.98594264, 7500: 0.07933521, 8000: 0.00129247, 8500: 0.00056306, 9000: 0.00036147, 9500: 0.00026517, 10000: 0.00020694, 10500: 0.00017334, 11000: 0.00014734, 11500: 0.00012765, 12000: 0.00011327, 12500: 0.00010193, 13000: 9.239e-05, 13500: 8.396e-05, 14000: 7.826e-05, 14500: 7.207e-05, 15000: 6.794e-05, 15500: 6.281e-05, 16000: 5.856e-05, 16500: 5.638e-05, 17000: 5.413e-05, 17500: 5.039e-05, 18000: 4.813e-05, 18500: 4.744e-05, 19000: 4.466e-05, 19500: 4.4e-05, 20000: 4.116e-05}
    with_noise_211 = {6000: 0.99999986, 6500: 0.99999979, 7000: 0.99999976, 7500: 0.99999959, 8000: 0.99999965, 8500: 0.99999966, 9000: 0.99999963, 9500: 0.99999952, 10000: 0.99999957, 10500: 0.99920179, 11000: 0.78420867, 11500: 0.05849153, 12000: 0.0015082, 12100: 0.00116306, 12200: 0.00093923, 12300: 0.00079525, 12400: 0.00068454, 12500: 0.00060226, 12600: 0.00053798, 12700: 0.0004894, 13100: 0.00034949, 13200: 0.00032877, 13300: 0.00030915, 13400: 0.00028646, 13500: 0.00027297, 13600: 0.00025996, 13700: 0.00024775, 13800: 0.00023362, 13900: 0.00022249, 14000: 0.00020998, 14500: 0.00017675, 15000: 0.00014924, 15500: 0.00012921, 16000: 0.00011647, 16500: 0.00010353, 17000: 9.448e-05, 17500: 8.664e-05, 18000: 7.725e-05, 18500: 7.341e-05, 19000: 6.929e-05, 19500: 6.472e-05, 20000: 6.118e-05}
    without_noise = {6000: 8.462e-05, 6500: 7.791e-05, 7000: 7.157e-05, 7500: 6.777e-05, 8000: 6.304e-05, 8500: 5.831e-05, 9000: 5.653e-05, 9500: 5.261e-05, 10000: 4.987e-05, 10500: 4.762e-05, 11000: 4.414e-05, 11500: 4.364e-05, 12000: 4.201e-05, 12500: 4.105e-05, 13000: 3.867e-05, 13500: 3.772e-05, 14000: 3.642e-05, 14500: 3.415e-05, 15000: 3.375e-05, 15500: 3.154e-05, 16000: 2.979e-05, 16500: 3.027e-05, 17000: 2.93e-05, 17500: 2.839e-05, 18000: 2.873e-05, 18500: 2.748e-05, 19000: 2.652e-05, 19500: 2.595e-05, 20000: 2.478e-05}
    fig, ax = pyplot.subplots()
    # To translate sigma to epsilon, use file: efficiency_privacy_tradeoff.py
    ax.plot([l for l in with_noise_211], [with_noise_211[l] for l in with_noise_211], marker='.', label="Noisy channel, $\epsilon=0.1$")
    ax.plot([l for l in with_noise_138], [with_noise_138[l] for l in with_noise_138], marker='.', label="Noisy channel, $\epsilon=0.15$")
    ax.plot([l for l in with_noise_100], [with_noise_100[l] for l in with_noise_100], marker='.', label="Noisy channel, $\epsilon=0.2$")
    ax.plot([l for l in without_noise], [without_noise[l] for l in without_noise], marker='.', label="Noiseless channel")

    first_x = 6_000
    first_y = without_noise[first_x]
    correlate_x = min(x for x in with_noise_138 if with_noise_138[x] < first_y)
    ax.text((first_x + correlate_x) / 2, first_y + 0.000005, "$\omega$", fontsize=17)
    ax.hlines(xmin=first_x, xmax=correlate_x, y=first_y, color="grey", linestyles="dashed", linewidth=2.8)

    ax.set_yticks([0, 0.0001, 0.0002, 0.0003, 0.0004, 0.0005])
    ax.set_yticklabels([f'{round(x * 100, 3) or 0}%' for x in pyplot.gca().get_yticks()])
    ax.set_xlabel("Total locked coins")
    ax.set_ylabel("Fail Rate")
    ax.set_ylim((0, 0.0005))
    ax.set_xlim((5_700, 20_250))
    fig.tight_layout()
    pyplot.legend(loc=(0.28, 0.62))
    fig.savefig(r'C:\Users\user\Downloads\fail_rate_vs_liquidity.pdf', format='pdf')
    pyplot.show()


if __name__ == '__main__':
    plot_success_ratio(list(range(6_000, 20_001, 500)))
