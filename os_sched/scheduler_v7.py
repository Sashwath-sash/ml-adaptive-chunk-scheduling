"""No-pilot dispatch planners for measured-data policy learning.

All task costs are estimates from input metadata available before dispatch.
The worker pool executes the real compiled-C kernels; timings include Python
planning, process creation, IPC, dispatch, and completion.
"""
import heapq
import multiprocessing as mp
import time

from .scheduler_v2 import _batch, _cpu_seconds, percentile
from .scheduler_v4 import estimated_cost, make_balanced_batches

POLICIES = (
    "fixed_4", "fixed_16", "fixed_32",
    "contig_8", "contig_16", "contig_32", "contig_64",
    "lpt_2", "lpt_4", "lpt_8", "lpt_16", "lpt_32", "lpt_64",
    "sorted_4", "sorted_8", "sorted_16",
)


def plan_batches(tasks, policy):
    if not tasks or policy not in POLICIES:
        raise ValueError("nonempty tasks and a supported policy required")
    family, size_text = policy.split("_")
    size = int(size_text)
    if family == "fixed":
        return [tasks[i:i + size] for i in range(0, len(tasks), size)]
    if family == "contig":
        return make_balanced_batches(tasks, 2, size)
    if family == "sorted":
        ordered = sorted(tasks, key=estimated_cost, reverse=True)
        return [ordered[i:i + size] for i in range(0, len(ordered), size)]
    # Longest-processing-time first: create roughly cost-equal batches rather
    # than simply cutting the input stream at a target-cost threshold.
    batch_count = min(size, len(tasks))
    bins = [[] for _ in range(batch_count)]
    loads = [0.0] * batch_count
    heap = [(0.0, index) for index in range(batch_count)]
    heapq.heapify(heap)
    for task in sorted(tasks, key=estimated_cost, reverse=True):
        load, index = heapq.heappop(heap)
        bins[index].append(task)
        loads[index] = load + estimated_cost(task)
        heapq.heappush(heap, (loads[index], index))
    batches = [batch for batch in bins if batch]
    batches.sort(key=lambda batch: sum(estimated_cost(task) for task in batch), reverse=True)
    assert sum(map(len, batches)) == len(tasks)
    return batches


def run_policy(tasks, workers, policy):
    if workers < 1:
        raise ValueError("workers >= 1 required")
    cpu_before = _cpu_seconds()
    started_ns = time.perf_counter_ns()
    batches = plan_batches(tasks, policy)
    planning_s = (time.perf_counter_ns() - started_ns) / 1e9
    with mp.Pool(workers) as pool:
        startup_s = (time.perf_counter_ns() - started_ns) / 1e9
        submitted_ns = time.perf_counter_ns()
        rows = pool.map(_batch, batches, chunksize=1)
    elapsed_s = (time.perf_counter_ns() - started_ns) / 1e9
    cpu_after = _cpu_seconds()
    cpu_s = max(0.0, cpu_after - cpu_before) if cpu_before is not None and cpu_after is not None else None
    latencies = [(row["ended_ns"] - submitted_ns) / 1e9 for row in rows]
    waits = [max(0.0, (row["started_ns"] - submitted_ns) / 1e9) for row in rows]
    return {
        "elapsed_s": elapsed_s,
        "checksum": sum(row["checksum"] for row in rows),
        "policy": policy,
        "planning_s": planning_s,
        "startup_s": startup_s,
        "cpu_s": cpu_s,
        "cpu_utilization_fraction": cpu_s / max(elapsed_s * workers, 1e-12) if cpu_s is not None else None,
        "batch_latency_p95_s": percentile(latencies, 95),
        "queue_wait_p95_s": percentile(waits, 95),
        "service_p95_s": percentile([row["service_s"] for row in rows], 95),
        "batch_count": len(batches),
    }
