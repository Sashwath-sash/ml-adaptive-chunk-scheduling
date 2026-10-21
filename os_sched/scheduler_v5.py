"""Measured hybrid and offline-trained policy selector for user-space task dispatch.

The selector sees only task metadata known before execution. It does not inspect
future runtimes or use evaluation labels. It chooses among fixed batching,
cost-aware batching, and a one-pilot tree-plus-cost hybrid.
"""
import math
import multiprocessing as mp
import time

from .scheduler_v2 import _batch, _cpu_seconds, _dispatch, percentile, run
from .scheduler_v4 import estimated_cost, make_balanced_batches, run_balanced
from .tree import DecisionTree

POLICIES = ("fixed_4", "balanced_16", "balanced_32", "balanced_64", "hybrid_once")
FEATURES = (
    "prime_fraction", "cost_cv", "max_to_mean_cost", "tail_cost_share",
    "head_cost_share", "largest_position", "task_count", "workers",
)


def task_features(tasks, workers):
    """Cheap, pre-dispatch features; no execution timing or evaluation leakage."""
    if not tasks or workers < 1:
        raise ValueError("nonempty tasks and workers >= 1 required")
    costs = [estimated_cost(task) for task in tasks]
    n = len(costs)
    total = sum(costs)
    mean = total / n
    variance = sum((value - mean) ** 2 for value in costs) / n
    tail = max(1, n // 8)
    return [
        sum(task.kernel == "prime" for task in tasks) / n,
        math.sqrt(variance) / max(mean, 1e-12),
        max(costs) / max(mean, 1e-12),
        sum(costs[-tail:]) / max(total, 1e-12),
        sum(costs[:tail]) / max(total, 1e-12),
        max(range(n), key=costs.__getitem__) / max(1, n - 1),
        float(n), float(workers),
    ]


def run_hybrid_once(tasks, workers, chunk_model):
    """One measured tree decision, then a single longest-estimated-cost-first map."""
    if not tasks or workers < 1 or chunk_model is None:
        raise ValueError("nonempty tasks, workers >= 1, and chunk model required")
    cpu_before = _cpu_seconds()
    start_ns = time.perf_counter_ns()
    pilot_count = min(len(tasks), 4 * workers * 2)
    with mp.Pool(workers) as pool:
        startup_s = (time.perf_counter_ns() - start_ns) / 1e9
        pilot = _dispatch(pool, tasks[:pilot_count], 4)
        remaining = tasks[pilot_count:]
        decision_ns = time.perf_counter_ns()
        features = [pilot["mean_task_s"], pilot["spread"],
                    pilot_count / max(pilot["elapsed_s"], 1e-12), 4.0,
                    len(remaining) / len(tasks)]
        chosen = min(64, max(1, int(chunk_model.predict_one(features))))
        target_batches = max(workers * 8, min(64, math.ceil(len(remaining) / chosen))) if remaining else 0
        decision_s = (time.perf_counter_ns() - decision_ns) / 1e9
        checksum = pilot["checksum"]
        latencies = list(pilot["batch_latencies_s"])
        waits = list(pilot["queue_wait_s"])
        services = list(pilot["service_s"])
        batch_count = len(services)
        if remaining:
            batches = make_balanced_batches(remaining, workers, target_batches)
            submitted_ns = time.perf_counter_ns()
            results = pool.map(_batch, batches, chunksize=1)
            checksum += sum(row["checksum"] for row in results)
            latencies.extend((row["ended_ns"] - submitted_ns) / 1e9 for row in results)
            waits.extend(max(0.0, (row["started_ns"] - submitted_ns) / 1e9) for row in results)
            services.extend(row["service_s"] for row in results)
            batch_count += len(results)
    elapsed_s = (time.perf_counter_ns() - start_ns) / 1e9
    cpu_after = _cpu_seconds()
    cpu_s = max(0.0, cpu_after - cpu_before) if cpu_before is not None and cpu_after is not None else None
    return {"elapsed_s": elapsed_s, "checksum": checksum, "startup_s": startup_s,
            "cpu_s": cpu_s, "cpu_utilization_fraction": cpu_s / max(elapsed_s * workers, 1e-12) if cpu_s is not None else None,
            "batch_latency_p50_s": percentile(latencies, 50),
            "batch_latency_p95_s": percentile(latencies, 95),
            "batch_latency_p99_s": percentile(latencies, 99),
            "queue_wait_p95_s": percentile(waits, 95),
            "service_p95_s": percentile(services, 95),
            "decision_p95_s": decision_s, "batch_count": batch_count,
            "pilot_tasks": pilot_count, "chosen_chunk": chosen,
            "target_batches": target_batches, "reason": "one_tree_decision_then_cost_order"}


def run_policy(tasks, workers, policy, chunk_model=None):
    if policy == "fixed_4":
        return run(tasks, workers, "fixed_4")
    if policy.startswith("balanced_") and policy in POLICIES:
        return run_balanced(tasks, workers, int(policy.split("_")[1]))
    if policy == "hybrid_once":
        return run_hybrid_once(tasks, workers, chunk_model)
    raise ValueError(f"unknown policy: {policy}")


def run_auto(tasks, workers, selector_model, chunk_model):
    """Include feature extraction and prediction in the complete invocation time."""
    if selector_model is None:
        raise ValueError("trained policy-selector model required")
    start_ns = time.perf_counter_ns()
    features = task_features(tasks, workers)
    feature_s = (time.perf_counter_ns() - start_ns) / 1e9
    decision_ns = time.perf_counter_ns()
    chosen = selector_model.predict_one(features)
    if chosen not in POLICIES:
        raise ValueError(f"selector returned unsupported policy: {chosen}")
    selection_s = (time.perf_counter_ns() - decision_ns) / 1e9
    result = run_policy(tasks, workers, chosen, chunk_model)
    return {**result, "elapsed_s": (time.perf_counter_ns() - start_ns) / 1e9,
            "selected_policy": chosen, "features": dict(zip(FEATURES, features)),
            "feature_s": feature_s, "selection_s": selection_s}
