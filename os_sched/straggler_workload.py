"""Deterministic CPU tasks with one rare expensive job near the tail."""
import random

from .workload import Task


def generate_tail_spike(count, base, seed, spike_factor=40):
    if count < 32 or base < 1 or spike_factor < 2:
        raise ValueError("count >= 32, positive base, spike_factor >= 2 required")
    rng = random.Random(seed)
    spike_index = count - 1 - rng.randrange(min(8, count))
    tasks = []
    for index in range(count):
        factor = spike_factor if index == spike_index else rng.uniform(.9, 1.1)
        tasks.append(Task(max(1, int(base * factor)), seed * 1000003 + index + 1))
    return tasks, spike_index
