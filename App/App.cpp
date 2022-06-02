#include <iostream>
#include <string>
#include <sstream>
#include <vector>
#include <getopt.h>
#include "sgx_urts.h"
#include "Enclave_u.h" // Headers for untrusted part (autogenerated by edger8r)
#include <pistache/endpoint.h>
#include <chrono>

using namespace Pistache;
using namespace std;

# define MAX_PATH FILENAME_MAX
# define ENCLAVE_FILENAME "enclave.signed.so"
# define ECC_PUB_KEY_SIZE 64
# define BLOCK_SIZE (ECC_PUB_KEY_SIZE / 2)
# define TRANSACTION_SIZE (4 + 16)
# define STATE_ENCRYPTED_SIZE 16

struct prevHtlc {
	uint8_t encrypted_output[TRANSACTION_SIZE];
	uint8_t encrypted_key[TRANSACTION_SIZE];
	bool is_positive;
};

struct inputs {
	uint8_t bob_dh_pub[ECC_PUB_KEY_SIZE];
	uint8_t encrypted_given_ammount[TRANSACTION_SIZE];
	uint8_t encrypted_key[TRANSACTION_SIZE];
	uint8_t prev_state[STATE_ENCRYPTED_SIZE];
	uint32_t prev_liquidity;
};

struct outputs {
	uint8_t result[TRANSACTION_SIZE];
	uint8_t key_encrypted_for_next[TRANSACTION_SIZE];
	uint8_t my_dh_pub[ECC_PUB_KEY_SIZE];
	uint8_t state[STATE_ENCRYPTED_SIZE];
};

sgx_enclave_id_t   eid = 0;
sgx_status_t ret = SGX_ERROR_UNEXPECTED; // status flag for enclave calls
sgx_launch_token_t token = { 0 };
int updated = 0;

chrono::steady_clock::time_point enclave_time_start;
chrono::steady_clock::time_point enclave_time_end;

// ocalls for printing string (C++ ocalls)
void ocall_print_error(const char *str){
    cerr << str << endl;
}

void ocall_print_string(const char *str){
    cout << str;
}

void ocall_println_string(const char *str){
    cout << str << endl;
}

void ocall_time_start(void){
    enclave_time_start = chrono::steady_clock::now();
}

void ocall_time_end(const char *str){
	enclave_time_end = chrono::steady_clock::now();
    cout << str << ": " << chrono::duration_cast<chrono::microseconds>(enclave_time_end - enclave_time_start).count() << "[µs]" << '\n';
	enclave_time_start = chrono::steady_clock::now();
}

uint64_t ocall_rdtsc(){
    unsigned int lo,hi;
    __asm__ __volatile__ ("rdtsc" : "=a" (lo), "=d" (hi));
    return ((uint64_t)hi << 32) | lo;
}

stringstream print_block(const uint8_t *str, size_t length){
	char const hex_chars[16] = { '0', '1', '2', '3', '4', '5', '6', '7', '8', '9', 'A', 'B', 'C', 'D', 'E', 'F' };
	stringstream data;

	for (size_t i = 0; i < length; i++)
	{
		data << hex_chars[ ( str[i] & 0xF0 ) >> 4 ];
    	data << hex_chars[ ( str[i] & 0x0F ) >> 0 ];
	}
	data << endl;
	return data;
}

int char2int(char input){
	if(input >= '0' && input <= '9')
		return input - '0';
	if(input >= 'A' && input <= 'F')
		return input - 'A' + 10;
	if(input >= 'a' && input <= 'f')
		return input - 'a' + 10;
	if (input == 0)
		return 0;
	cout << "Warning: Got invalid hex:" << (int)input << endl;
	return 0;
}

void load_from_hex(string hex, uint8_t* arr) {
	const char* hex_char = hex.c_str();
	for (int i = 0; i < hex.length(); i += 2) {
		arr[i/2] = char2int(hex_char[i])*16 + char2int(hex_char[i+1]);
	}
}

void ocall_print_char(const char *str, size_t length){
    print_block((uint8_t*)str, length);
}

string exec_enclave(string bob_dh_pub_str, string encrypted_given_ammount_str, string encrypted_key_str, string prev_liquidity_str, string prev_htlcs_str, string prev_state_str) {
	uint8_t encrypted_given_ammount[TRANSACTION_SIZE] = { 0 };
	uint8_t bob_dh_pub[ECC_PUB_KEY_SIZE] = { 0 };
	uint8_t encrypted_key[TRANSACTION_SIZE] = { 0 };
	uint8_t prev_state[STATE_ENCRYPTED_SIZE] = { 0 };
	size_t prev_liquidity = 0;
	std::vector<prevHtlc> htlcs;
	inputs input = {};
	uint8_t raw_input[sizeof(inputs)];
	string segment;

	// parse input
	load_from_hex(bob_dh_pub_str, bob_dh_pub);
	load_from_hex(encrypted_given_ammount_str, encrypted_given_ammount);
	load_from_hex(encrypted_key_str, encrypted_key);
	load_from_hex(prev_state_str, prev_state);
	prev_liquidity = stoi(prev_liquidity_str);
	stringstream hex = stringstream(prev_htlcs_str);
	while(std::getline(hex, segment, '#')){
		prevHtlc htlc = {};
		if (segment.length() == 0) {
		    continue;
		}
		if (segment.length() != TRANSACTION_SIZE * 4 + 1 && segment.length() != TRANSACTION_SIZE * 4) {
			cout << "Bad segment size in prev_htlcs_str: " << segment.length() << " data: " << segment << endl;
		} else {
			load_from_hex(segment.substr(0, TRANSACTION_SIZE * 2), htlc.encrypted_output);
			load_from_hex(segment.substr(TRANSACTION_SIZE * 2, TRANSACTION_SIZE * 4), htlc.encrypted_key);
			if (segment.length() == TRANSACTION_SIZE * 4 || segment.at(TRANSACTION_SIZE * 4) == '0') {
			    htlc.is_positive = true;
			} else {
			    htlc.is_positive = false;
			}
			htlcs.push_back(htlc);
		}
	}


    // execute the enclave main function
	memcpy(input.bob_dh_pub, bob_dh_pub, ECC_PUB_KEY_SIZE);
	memcpy(input.encrypted_given_ammount, encrypted_given_ammount, TRANSACTION_SIZE);
	memcpy(input.encrypted_key, encrypted_key, TRANSACTION_SIZE);
	memcpy(input.prev_state, prev_state, STATE_ENCRYPTED_SIZE);
	input.prev_liquidity = prev_liquidity;
	memcpy(raw_input, &input, sizeof(inputs));
	outputs to_output = {};

	 chrono::steady_clock::time_point begin = chrono::steady_clock::now();
	ret = ecall_exec(eid, raw_input, sizeof(inputs), (uint8_t*)htlcs.data(), sizeof(prevHtlc) * htlcs.size(), (uint8_t*)&to_output);
    if (ret != SGX_SUCCESS) {
        begin = chrono::steady_clock::now();
        sgx_destroy_enclave(eid);
        ret = sgx_create_enclave(ENCLAVE_FILENAME, SGX_DEBUG_FLAG, &token, &updated, &eid, NULL);
        if (ret != SGX_SUCCESS) {
            cerr << "Enclave reset after error failed" << endl;
            return "Enclave Fatal Failure (create)";
        }
        cout << "SGX restart = " << chrono::duration_cast<chrono::microseconds>(chrono::steady_clock::now() - begin).count() << "[µs]" << endl;
        return "Enclave Failure";
    }
//	 cout << "SGX exec = " << chrono::duration_cast<chrono::microseconds>(chrono::steady_clock::now() - begin).count() << "[µs]" << endl;

	stringstream out;
	out << "output:" << endl;
	out << print_block(to_output.result, sizeof(to_output.result)).str();
	out << "key_encrypted_for_next:" << endl;
	out << print_block(to_output.key_encrypted_for_next, sizeof(to_output.key_encrypted_for_next)).str();
	out << "my_dh_pub:" << endl;
	out << print_block(to_output.my_dh_pub, sizeof(to_output.my_dh_pub)).str();
	out << "state:" << endl;
	out << print_block(to_output.state, sizeof(to_output.state)).str();
	return out.str();
}

struct EnclaveHandler : public Http::Handler {
  HTTP_PROTOTYPE(EnclaveHandler)
  void onRequest(const Http::Request& req, Http::ResponseWriter writer) override{
	try{
		string bob_dh_pub_str = req.query().get("bob_dh_pub").value();
		string encrypted_given_ammount_str = req.query().get("encrypted_given_ammount").value();
		string encrypted_key_str = req.query().get("encrypted_key").value();
		string prev_liquidity_str = req.query().get("prev_liquidity").value();
		string prev_state_str = req.query().get("prev_state").value_or("");
		string prev_htlcs_str = req.body();

		if (
			bob_dh_pub_str.length() != 2 * ECC_PUB_KEY_SIZE ||
			encrypted_given_ammount_str.length() != 2 * TRANSACTION_SIZE ||
			encrypted_key_str.length() != 2 * TRANSACTION_SIZE ||
			prev_liquidity_str.length() > 10
			) {
			string failure = "Input failure";
			if (bob_dh_pub_str.length() != 2 * ECC_PUB_KEY_SIZE) failure += " bob_dh_pub_str";
			if (encrypted_given_ammount_str.length() != 2 * TRANSACTION_SIZE) failure += " encrypted_given_ammount_str";
			if (encrypted_key_str.length() != 2 * TRANSACTION_SIZE) failure += " encrypted_key_str";
			if (prev_liquidity_str.length() > 10) failure += " prev_liquidity_str" + prev_liquidity_str;
			writer.send(Http::Code::Ok, failure);
			return;
		}
		
		string enclave_out = exec_enclave(bob_dh_pub_str, encrypted_given_ammount_str, encrypted_key_str, prev_liquidity_str, prev_htlcs_str, prev_state_str);
		writer.send(Http::Code::Ok, enclave_out);
	} catch (const std::exception& exc) {
		cout << "Exception" << exc.what() << endl;
		writer.send(Http::Code::Ok, "Unexpected failure");
	}catch(...) {
		cout << "Uexpected failure" << endl;
		writer.send(Http::Code::Ok, "Unexpected failure");
	}
  }
};

// Application entry
int main(int argc, char *argv[]){
	uint64_t command;

	string bob_dh_pub_str = "";
	string encrypted_given_ammount_str;
	string encrypted_key_str;
	string prev_liquidity_str;
	string prev_htlcs_str;
	string prev_state_str = "";

	char usage[] = "usage: %s [-h bob_dh_pub] [-c encrypted_given_ammount] [-k encrypted_key] [-l prev_liquidity] [-p prev_htlcs] [-s prev_state] \n";
	while ((command = getopt(argc, argv, "h:c:l:k:p:s:")) != -1)
		switch (command)
		{
		case 'h':
			bob_dh_pub_str = string(optarg);
			break;
		case 'c':
			encrypted_given_ammount_str = string(optarg);
			break;
		case 'k':
			encrypted_key_str = string(optarg);
			break;
		case 'l':
			prev_liquidity_str = string(optarg);
			break;
		case 'p':
			prev_htlcs_str = string(optarg);
			break;
		case 's':
			prev_state_str = string(optarg);
			break;
		default:
			abort();
		}

	chrono::steady_clock::time_point begin = chrono::steady_clock::now();

    // Initialize the enclave
    ret = sgx_create_enclave(ENCLAVE_FILENAME, SGX_DEBUG_FLAG, &token, &updated, &eid, NULL);
    if (ret != SGX_SUCCESS) {
        cerr << "Error: creating enclave" << endl;
        return -1;
    }
	
	chrono::steady_clock::time_point end = chrono::steady_clock::now();
	cout << "SGX init = " << chrono::duration_cast<chrono::microseconds>(end - begin).count() << "[µs]" << endl;

	if (bob_dh_pub_str == "") {
		Pistache::Address addr(Pistache::Ipv4::any(), Pistache::Port(9080));
		EnclaveHandler handler;
		auto opts = Pistache::Http::Endpoint::options()
		.maxRequestSize(32 * 1024 * 1024)  // 32 MB
		.flags(Pistache::Tcp::Options::ReuseAddr);
		Http::Endpoint server(addr);
		server.init(opts);
		server.setHandler(Pistache::Http::make_handler<EnclaveHandler>());
		server.serve();
	} else {
		cout << exec_enclave(bob_dh_pub_str, encrypted_given_ammount_str, encrypted_key_str, prev_liquidity_str, prev_htlcs_str, prev_state_str);
	}

	begin = chrono::steady_clock::now();
    // Destroy the enclave
    sgx_destroy_enclave(eid);
    if (ret != SGX_SUCCESS) {
        cerr << "Error: destroying enclave" << endl;
        return -1;
    }

	end = chrono::steady_clock::now();
	cout << "Destroy enclave = " << chrono::duration_cast<chrono::microseconds>(end - begin).count() << "[µs]" << endl;

    return 0;
}