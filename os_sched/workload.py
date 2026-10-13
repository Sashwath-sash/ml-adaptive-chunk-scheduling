import random
from dataclasses import dataclass


@dataclass(frozen=True)
class Task:
    work: int
    seed: int
    kernel: str = "synthetic"


def generate(kind: str, count: int, base: int, seed: int) -> list[Task]:
    """Generate deterministic CPU work units. Work is an iteration count, not a label."""
    if kind not in {"uniform", "moderate", "high", "phase_shift", "prime_scan"}:
        raise ValueError(kind)
    rng = random.Random(seed)
    tasks = []
    for i in range(count):
        if kind == "prime_scan":
            # A genuine prime-counting algorithm over disjoint integer ranges.
            # The later ranges cost more due to more possible trial divisors.
            start = 1_000_000 + (seed % 100) * 10_000 + i * max(1, base)
            tasks.append(Task(max(1, base), start, "prime"))
            continue
        if kind == "uniform":
            factor = 1.0
        elif kind == "moderate":
            factor = rng.uniform(0.5, 1.5)
        elif kind == "high":
            factor = 0.2 if rng.random() < 0.7 else 2.87
        else:
            # The second half changes distribution without changing total task count.
            factor = 0.45 if i < count // 2 else (0.2 if rng.random() < 0.5 else 2.8)
        tasks.append(Task(max(1, int(base * factor)), seed * 1000003 + i + 1))
    return tasks
