#include <iostream>
#include <string>
#include <sstream>
#include <vector>
#include <getopt.h>
#include <chrono>
#include <random>
#include "../Enclave/tree.cpp"

using namespace std;


void print_bits(unsigned num){
	unsigned n = num;
	string s;
	while (n != 0){
		s = to_string(n%2) + s;
		n = n/2;
	}
	cout << s << endl;
}


int main(int argc, char *argv[]){
    unsigned seed_key = 1234;
    double expected, actual;
    unsigned input;


    input = 0b1000101011;
    expected = 0;
    expected += single_node_noise(0b10, seed_key);
    expected += single_node_noise(0b100010, seed_key);
    expected += single_node_noise(0b10001010, seed_key);
    expected += single_node_noise(0b11, seed_key);
    actual = compute_tree_noise(input, seed_key, 10);
    cout << "Test Passed: " << (expected == actual) << endl;


    input = 0b1000101000;
    expected = 0;
    expected += single_node_noise(0b10, seed_key);
    expected += single_node_noise(0b100010, seed_key);
    expected += single_node_noise(0b10001010, seed_key);
    actual = compute_tree_noise(input, seed_key, 10);
    cout << "Test Passed: " << (expected == actual) << endl;


    return 0;
}