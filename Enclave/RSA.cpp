#include <stdio.h>
#include <stdlib.h>
#include <ctype.h>
#include <math.h>
#include "Enclave_t.h"
 

class RSA {
 
 public:
    RSA(){}

    uint64_t FastExponention(uint64_t bit, uint64_t n, uint64_t * y, uint64_t * a)
    {
        if (bit == 1)
            *y = (*y * (*a)) % n;
        
        *a = (*a) * (*a) % n;
    }
    uint64_t FindT(uint64_t a, uint64_t m, uint64_t n)
    {
        uint64_t r;
        uint64_t y = 1;
    
        while (m > 0) {
            r = m % 2;
            FastExponention(r, n, &y, &a);
            m = m / 2;
        }
        return y;
    }
    
    void Encryption(uint16_t* input, size_t input_size, uint64_t public_key, uint64_t n, uint64_t* output)
    {
        for (int i=0; i < input_size; i++){
            output[i] = FindT(input[i], public_key, n);
        }
    }

    void Decryption(uint64_t * input, size_t input_size, uint64_t private_key, uint64_t n, uint16_t* output)
    {
        for (int i=0; i < input_size; i++){
            output[i] = FindT(input[i], private_key, n);
        }
    }
};