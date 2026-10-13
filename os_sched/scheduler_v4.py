"""Single-dispatch estimated-cost batching with longest batches first.

Unlike the decision-tree methods, this algorithm uses task metadata available
before execution and never stops the pool for a feedback round. It is an
application-level Linux process-pool scheduler, not a kernel modification.
"""
import math
import multiprocessing as mp
import time

from .scheduler_v2 import _batch, _cpu_seconds, percentile


def estimated_cost(task):
    if task.kernel == "prime":
        # Trial division cost grows roughly with sqrt(candidate magnitude).
        return task.work * math.sqrt(max(1, task.seed + task.work / 2))
    return float(task.work)


def make_balanced_batches(tasks, workers, target_batches, max_items=32, longest_first=True):
    if workers < 1 or target_batches < 1 or max_items < 1 or not tasks:
        raise ValueError("positive workers/batches/max_items and nonempty tasks required")
    target_cost = sum(estimated_cost(task) for task in tasks) / target_batches
    batches, current, cost = [], [], 0.0
    for task in tasks:
        estimate = estimated_cost(task)
        if current and (cost + estimate > target_cost or len(current) >= max_items):
            batches.append(current)
            current, cost = [], 0.0
        current.append(task)
        cost += estimate
    if current:
        batches.append(current)
    if longest_first:
        # Pool.map assigns the first available worker; long jobs first reduces
        # the chance that one large final batch determines the overall finish.
        batches.sort(key=lambda batch: sum(estimated_cost(task) for task in batch), reverse=True)
    assert sum(map(len, batches)) == len(tasks)
    return batches


def run_balanced(tasks, workers, target_batches=16, max_items=32, longest_first=True):
    cpu_before = _cpu_seconds()
    started_ns = time.perf_counter_ns()
    batches = make_balanced_batches(tasks, workers, target_batches, max_items, longest_first)
    with mp.Pool(workers) as pool:
        startup_s = (time.perf_counter_ns() - started_ns) / 1e9
        submitted_ns = time.perf_counter_ns()
        results = pool.map(_batch, batches, chunksize=1)
    elapsed_s = (time.perf_counter_ns() - started_ns) / 1e9
    cpu_after = _cpu_seconds()
    cpu_s = max(0.0, cpu_after - cpu_before) if cpu_before is not None and cpu_after is not None else None
    latencies = [(r["ended_ns"] - submitted_ns) / 1e9 for r in results]
    waits = [max(0.0, (r["started_ns"] - submitted_ns) / 1e9) for r in results]
    services = [r["service_s"] for r in results]
    return {"elapsed_s": elapsed_s, "checksum": sum(r["checksum"] for r in results),
            "startup_s": startup_s, "cpu_s": cpu_s,
            "cpu_utilization_fraction": cpu_s / max(elapsed_s * workers, 1e-12) if cpu_s is not None else None,
            "batch_latency_p95_s": percentile(latencies, 95),
            "queue_wait_p95_s": percentile(waits, 95),
            "service_p95_s": percentile(services, 95),
            "batch_count": len(batches),
            "batch_size_min": min(map(len, batches)),
            "batch_size_max": max(map(len, batches))}
