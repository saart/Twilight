import math
import scipy.stats
import seaborn
from matplotlib import pyplot
seaborn.set()

N = 28
m = 1  # Number of coins
n = 1  # Number of overall transactions

delta_sec = {
    10**-5: "$e^{-5}$",
    10**-7: "$e^{-7}$",
    10**-9: "$e^{-9}$"
}  # gives delta(security)
delta_eff = {
    # 0.1: "$10^{-1}$",
    # 0.01: "$10^{-2}$",
    0.001: "$10^{-3}$",
    0.0001: "$10^{-4}$",
    0.00001: "$10^{-5}$",
    # 0.000001: "$10^{-6}$",
    # 0.0000001: "$10^{-7}$",
}  # gives delta(efficiency)

SIGMA_VALUES = list(range(10, 1500, 2))


def calc_c(sigma, mu, delta):
    # binary search on Theorem 3 \delta
    lower = 3
    upper = 10
    for _ in range(100):
        c = (upper + lower) / 2
        curr = gaussCDF(mu, sigma**2, mu-c*sigma)
        if curr < delta - 0.000000000000001:
            upper = (lower+upper)/2
        elif curr > delta + 0.000000000000001:
            lower = (lower+upper)/2
        else:
            return c
    raise Exception()


def calc_t(sigma, mu, delta):
    # binary search on Theorem 4 \Delta
    lower = 10
    upper = 1_000_000
    for _ in range(200):
        t = (upper + lower) / 2
        curr = gaussCDF(mu * N, (sigma ** 2) * N, mu * N - t)
        if curr < delta - 0.000000000001:
            upper = (lower+upper)/2
        elif curr > delta + 0.000000000001:
            lower = (lower+upper)/2
        else:
            return t
    raise Exception()


def calc_mu(sigma):
    return (sigma * 10) / (N ** 0.5)


# Theorem 3 - privacy
def thm3_epsilon_delta(sigma, delta_sec, r=1, l=1):
    Mu = calc_mu(sigma)
    c = calc_c(sigma, Mu, delta_sec)
    # return \epsilon, \delta
    log_t = N - 6
    return (math.log(1 + (m * c * ((l * log_t) ** 0.5))/(sigma * (r ** 0.5)) + (l * log_t * (m ** 2))/(2 * (sigma ** 2))),
            2 * gaussCDF(Mu, r * log_t * (sigma ** 2), Mu - c * ((r * log_t) ** 0.5) * sigma))


# Theorem 4 - efficiency
def thm4_efficieny_confidence(sigma, delta_eff):
    Mu = calc_mu(sigma)
    t = calc_t(sigma, Mu, delta_eff)
    # return \omega, \Delta
    return ((Mu * N) + t,
            1 - n * gaussCDF(Mu * N, (sigma ** 2) * N, Mu * N + t))


def gaussCDF(mu, signma_square, until):
    return scipy.stats.norm.cdf(until, loc=mu, scale=signma_square ** 0.5)


def present_2d(thm3, thm4):
    mid = list(delta_sec)[1]
    index = min(range(len(thm3[mid])), key=lambda i: math.fabs(thm3[mid][i] - 0.15))
    print(index, SIGMA_VALUES[index])
    max_x_value = thm4[0.001][index] * 3.5
    for d_sec, _ in delta_sec.items():
        fig, ax1 = pyplot.subplots(dpi=100)
        ax1.set_xlabel("Additional locked coins", fontsize=24)
        ax1.set_ylabel('$\\epsilon$', fontsize=28, rotation=0, labelpad=20)
        ax1.set_yticks([0.1, 0.2, 0.3, 0.4, 0.5])
        ax1.tick_params(axis='both', which='major', labelsize=18)
        ax1.set_ylim((0, 0.5))
        for d_eff, d_eff_str in delta_eff.items():
            x_axis = [t for t in thm4[d_eff] if t < max_x_value]
            ax1.plot(x_axis, [t for t, _ in zip(thm3[d_sec], x_axis)],
                     label=f"Inefficiency $\Delta=$ {d_eff_str}")
        point_x = round(thm4[0.001][index])
        point_y = round(thm3[d_sec][index], 4)
        print(point_x, point_y)
        ax1.scatter([point_x], [point_y], color="black", s=20, zorder=5)
        ax1.annotate(f'({round(point_x, -1)}, {point_y:.3})', (point_x, point_y), fontsize=22)
        fig.legend(loc='best', fontsize=18)
        fig.tight_layout()
        fig_suffix = round(math.log(d_sec, 10)) - 1
        fig.savefig(fr'C:\Users\user\Downloads\efficiency_privacy_thm3-4_64_{fig_suffix}.pdf', format='pdf')

    pyplot.show()


def main_2d():
    print("Delta=10^-2", thm4_efficieny_confidence(128, 0.01)[0])
    print("Delta=10^-10", thm4_efficieny_confidence(128, 10 ** -10)[0])
    thm3 = {d_sec: [thm3_epsilon_delta(s, d_sec)[0] for s in SIGMA_VALUES] for d_sec in delta_sec}
    thm4 = {d_eff: [thm4_efficieny_confidence(s, d_eff)[0] for s in SIGMA_VALUES] for d_eff in delta_eff}
    present_2d(thm3, thm4)


def print_locked_amount_by_disjoint_route():

    disjoint_routes_to_amount = {}
    for l in range(1, 6):
        for r in range(1, 11):
            sigma = list(range(10, 1000, 3))
            thm3 = {d_sec: [thm3_epsilon_delta(s, d_sec, r=r, l=l)[0] for s in sigma] for d_sec in delta_sec}
            thm4 = {d_similatiry: [thm4_efficieny_confidence(s, d_similatiry)[0] for s in sigma] for d_similatiry in [0.001]}

            for d_sec in delta_sec:
                index = min(range(len(thm3[d_sec])), key=lambda i: math.fabs(thm3[d_sec][i] - 0.15))
                # print(f"l={l}, r={r}, index={index}")
                point_x = thm4[0.001][index]
                disjoint_routes_to_amount[(l, r, d_sec)] = point_x
    print(disjoint_routes_to_amount)
    # disjoint_routes_to_amount = {(1, 1, 0.0001): 7550.102838369193, (1, 1, 1e-06): 9628.112815620349, (1, 1, 1e-08): 11290.520762497026, (1, 2, 0.0001): 5264.291889586106, (1, 2, 1e-06): 6718.898864930854, (1, 2, 1e-08): 7965.7048396401315, (1, 3, 0.0001): 4433.087901595996, (1, 3, 1e-06): 5472.092890221575, (1, 3, 1e-08): 6511.097878847153, (1, 4, 0.0001): 3809.6849142413566, (1, 4, 1e-06): 4848.689902866935, (1, 4, 1e-08): 5679.893876305275, (1, 5, 0.0001): 3394.082927522187, (1, 5, 1e-06): 4433.087901595996, (1, 5, 1e-08): 5056.490888950636, (1, 6, 0.0001): 3186.2819414384876, (1, 6, 1e-06): 4017.485914876827, (1, 6, 1e-08): 4640.888902231465, (1, 7, 0.0001): 2978.480940803018, (1, 7, 1e-06): 3601.883928157657, (1, 7, 1e-08): 4433.087901595996, (1, 8, 0.0001): 2770.679940167548, (1, 8, 1e-06): 3394.082927522187, (1, 8, 1e-08): 4017.485914876827, (1, 9, 0.0001): 2562.878946807963, (1, 9, 1e-06): 3186.2819414384876, (1, 9, 1e-08): 3809.6849142413566, (1, 10, 0.0001): 2562.878946807963, (1, 10, 1e-06): 3186.2819414384876, (1, 10, 1e-08): 3601.883928157657, (2, 1, 0.0001): 10667.11777514239, (2, 1, 1e-06): 13576.331696728344, (2, 1, 1e-08): 16069.943646146903, (2, 2, 0.0001): 7550.102838369193, (2, 2, 1e-06): 9628.112815620349, (2, 2, 1e-08): 11290.520762497026, (2, 3, 0.0001): 6303.2968636599135, (2, 3, 1e-06): 7965.7048396401315, (2, 3, 1e-08): 9212.51081434941, (2, 4, 0.0001): 5472.092890221575, (2, 4, 1e-06): 6926.699851014553, (2, 4, 1e-08): 7965.7048396401315, (2, 5, 0.0001): 4848.689902866935, (2, 5, 1e-06): 6095.495877576214, (2, 5, 1e-08): 7134.500866201793, (2, 6, 0.0001): 4433.087901595996, (2, 6, 1e-06): 5679.893876305275, (2, 6, 1e-08): 6511.097878847153, (2, 7, 0.0001): 4225.286915512296, (2, 7, 1e-06): 5264.291889586106, (2, 7, 1e-08): 6095.495877576214, (2, 8, 0.0001): 3809.6849142413566, (2, 8, 1e-06): 4848.689902866935, (2, 8, 1e-08): 5679.893876305275, (2, 9, 0.0001): 3601.883928157657, (2, 9, 1e-06): 4640.888902231465, (2, 9, 1e-08): 5472.092890221575, (2, 10, 0.0001): 3601.883928157657, (2, 10, 1e-06): 4433.087901595996, (2, 10, 1e-08): 5264.291889586106, (3, 1, 0.0001): 12952.928709373706, (3, 1, 1e-06): 16485.545676521382, (3, 1, 1e-08): 19602.560613294576, (3, 2, 0.0001): 9212.51081434941, (3, 2, 1e-06): 11706.122734664428, (3, 2, 1e-08): 13784.132711915585, (3, 3, 0.0001): 7550.102838369193, (3, 3, 1e-06): 9628.112815620349, (3, 3, 1e-08): 11290.520762497026, (3, 4, 0.0001): 6718.898864930854, (3, 4, 1e-06): 8381.306840911071, (3, 4, 1e-08): 9835.91380170405, (3, 5, 0.0001): 5887.694891492514, (3, 5, 1e-06): 7550.102838369193, (3, 5, 1e-08): 8796.908813078471, (3, 6, 0.0001): 5472.092890221575, (3, 6, 1e-06): 6926.699851014553, (3, 6, 1e-08): 8173.505825723832, (3, 7, 0.0001): 5056.490888950636, (3, 7, 1e-06): 6303.2968636599135, (3, 7, 1e-08): 7550.102838369193, (3, 8, 0.0001): 4848.689902866935, (3, 8, 1e-06): 6095.495877576214, (3, 8, 1e-08): 7134.500866201793, (3, 9, 0.0001): 4433.087901595996, (3, 9, 1e-06): 5679.893876305275, (3, 9, 1e-08): 6718.898864930854, (3, 10, 0.0001): 4225.286915512296, (3, 10, 1e-06): 5472.092890221575, (3, 10, 1e-08): 6303.2968636599135, (4, 1, 0.0001): 15030.938686624864, (4, 1, 1e-06): 19186.9585829201, (4, 1, 1e-08): 22511.774534880537, (4, 2, 0.0001): 10667.11777514239, (4, 2, 1e-06): 13576.331696728344, (4, 2, 1e-08): 16069.943646146903, (4, 3, 0.0001): 8796.908813078471, (4, 3, 1e-06): 11082.719747309788, (4, 3, 1e-08): 13160.729724560944, (4, 4, 0.0001): 7550.102838369193, (4, 4, 1e-06): 9628.112815620349, (4, 4, 1e-08): 11290.520762497026, (4, 5, 0.0001): 6926.699851014553, (4, 5, 1e-06): 8589.107826994772, (4, 5, 1e-08): 10251.515802974987, (4, 6, 0.0001): 6303.2968636599135, (4, 6, 1e-06): 7965.7048396401315, (4, 6, 1e-08): 9420.31180043311, (4, 7, 0.0001): 5887.694891492514, (4, 7, 1e-06): 7342.301852285492, (4, 7, 1e-08): 8589.107826994772, (4, 8, 0.0001): 5472.092890221575, (4, 8, 1e-06): 6926.699851014553, (4, 8, 1e-08): 8173.505825723832, (4, 9, 0.0001): 5264.291889586106, (4, 9, 1e-06): 6511.097878847153, (4, 9, 1e-08): 7757.903853556432, (4, 10, 0.0001): 5056.490888950636, (4, 10, 1e-06): 6303.2968636599135, (4, 10, 1e-08): 7342.301852285492, (5, 1, 0.0001): 16693.34663350154, (5, 1, 1e-06): 21472.769575358492, (5, 1, 1e-08): 25213.18749948633, (5, 2, 0.0001): 11913.923749851667, (5, 2, 1e-06): 15238.739701812101, (5, 2, 1e-08): 17940.152608210818, (5, 3, 0.0001): 9835.91380170405, (5, 3, 1e-06): 12537.326737206306, (5, 3, 1e-08): 14615.336714457462, (5, 4, 0.0001): 8589.107826994772, (5, 4, 1e-06): 10874.918790329628, (5, 4, 1e-08): 12745.127752393546, (5, 5, 0.0001): 7757.903853556432, (5, 5, 1e-06): 9628.112815620349, (5, 5, 1e-08): 11498.321777684267, (5, 6, 0.0001): 7134.500866201793, (5, 6, 1e-06): 8796.908813078471, (5, 6, 1e-08): 10459.316789058688, (5, 7, 0.0001): 6511.097878847153, (5, 7, 1e-06): 8173.505825723832, (5, 7, 1e-08): 9628.112815620349, (5, 8, 0.0001): 6095.495877576214, (5, 8, 1e-06): 7757.903853556432, (5, 8, 1e-08): 9004.70982826571, (5, 9, 0.0001): 5887.694891492514, (5, 9, 1e-06): 7342.301852285492, (5, 9, 1e-08): 8589.107826994772, (5, 10, 0.0001): 5472.092890221575, (5, 10, 1e-06): 6926.699851014553, (5, 10, 1e-08): 8173.505825723832}

    for d_sec in delta_sec:
        fig, ax1 = pyplot.subplots(dpi=100)
        ax1.set_xlabel("# disjoint routes", fontsize=24)
        ax1.set_ylabel('Additional locked coins', fontsize=24)
        ax1.tick_params(axis='both', which='major', labelsize=18)
        for l in range(1, 6):
            indices = [(l, r, d_sec) for r in range(1, 11)]
            ax1.plot(list(range(1, 11)), [disjoint_routes_to_amount[t] for t in indices],
                     label=f"{l} inter-relay channel{'s' if l > 1 else ''}")
        ax1.set_xlim((0, 10.5))
        ax1.set_xticks(list(range(1, 11)))
        ax1.set_yticks([0, 5000, 10000, 15000, 20000, 25000])
        ax1.set_yticklabels(["0", "5k", "10k", "15k", "20k", "25k"])
        fig.tight_layout()
        fig_suffix = round(math.log(d_sec, 10)) - 1
        fig.legend(fontsize=18)
        fig.savefig(fr'C:\Users\user\Downloads\escrow_to_r_{fig_suffix}.pdf', format='pdf')

    pyplot.show()


if __name__ == '__main__':
    main_2d()
    # print_locked_amount_by_disjoint_route()

    print(f"Epsilon for sigma 211 is: {thm3_epsilon_delta(211, 10 ** -7)}")
    print(f"Epsilon for sigma 138 is: {thm3_epsilon_delta(138, 10 ** -7)}")
    print(f"Epsilon for sigma 100 is: {thm3_epsilon_delta(100, 10 ** -7)}")
    print(f"omega for sigma 100 is: {thm4_efficieny_confidence(100, 0.001)}")
