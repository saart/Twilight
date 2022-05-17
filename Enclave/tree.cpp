#include <vector>
#include <string>
#include <random>

# define NOISE_TREE_HEIGHT 32
# define TREE_POISSON_LAMBDA 100


std::poisson_distribution<int> distribution(TREE_POISSON_LAMBDA);


double single_node_noise(unsigned node, unsigned seed_key){
    std::default_random_engine generator(seed_key + node);
    return distribution(generator);
}

double compute_tree_noise(unsigned timestamp, unsigned seed_key, size_t tree_height){
    // first find the nodes to use. We do so by traversing the binary representation
	// of the current time. In "0"s we don't add any node, otherwise, if all the rest
	// of the bits are "1"s then we will add the current node, otherwise just take the
	// left sibling.
	double total = 0.0;
	for (size_t i = 0; i < tree_height; i++) {
		auto bits_to_the_right = tree_height - i;
		unsigned rightmost_bits = timestamp % (1 << bits_to_the_right);
		unsigned leftmost_bits = timestamp / (1 << bits_to_the_right);
		if (rightmost_bits + 1 == (1 << bits_to_the_right)) {
			// If all the remaining bits (after the i'th bit) are 1s.
			total += single_node_noise(rightmost_bits, seed_key);
			return total;
		} else if (leftmost_bits % 2 == 1) {
			// If the i'th bit is 1
			total += single_node_noise(leftmost_bits << 1, seed_key);
		}
	}

    return total;
}

double compute_tree_noise(unsigned timestamp, unsigned seed_key) {
	return compute_tree_noise(timestamp, seed_key, NOISE_TREE_HEIGHT);
}