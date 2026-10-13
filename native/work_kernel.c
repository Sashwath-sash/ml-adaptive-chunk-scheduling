#include <stdint.h>

/* Deterministic integer work. The result depends on both seed and iteration count. */
uint64_t cpu_work(uint64_t iterations, uint64_t seed) {
    uint64_t x = seed ^ UINT64_C(0x9e3779b97f4a7c15);
    for (uint64_t i = 0; i < iterations; ++i) {
        x ^= x >> 12;
        x ^= x << 25;
        x ^= x >> 27;
        x *= UINT64_C(0x2545f4914f6cdd1d);
    }
    return x;
}

/* Real independent CPU task: count primes in [start, start + count).
   The integer result is deterministic and can be checked across schedulers. */
uint64_t prime_count(uint64_t count, uint64_t start) {
    uint64_t total = 0;
    for (uint64_t value = start; value < start + count; ++value) {
        if (value < 2) continue;
        uint64_t prime = 1;
        for (uint64_t divisor = 2; divisor <= value / divisor; ++divisor) {
            if (value % divisor == 0) { prime = 0; break; }
        }
        total += prime;
    }
    return total;
}
