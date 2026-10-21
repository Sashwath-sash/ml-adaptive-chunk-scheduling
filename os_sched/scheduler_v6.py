"""Live measured-metrics CART scheduler with one pilot and cost-aware choices.

All model inputs are either measured from completed compiled-C tasks on this
invocation or are metadata known before the remaining tasks execute. The
decision changes application-level batching, never the Linux CPU scheduler.
"""
import math
import multiprocessing as mp
import statistics
import time

from .scheduler_v2 import _batch, _cpu_seconds, _dispatch, percentile
from .scheduler_v4 import estimated_cost, make_balanced_batches

POLICIES = ("fixed_4", "cost_16", "cost_32", "cost_64")
FEATURES = (
    "pilot_mean_task_s", "pilot_service_cv", "pilot_throughput_tps",
    "pilot_queue_wait_p95_s", "pilot_batch_latency_p95_s",
    "pilot_service_p95_s", "remaining_cost_cv", "remaining_max_to_mean",
    "remaining_tail_cost_share", "prime_fraction", "remaining_fraction",
    "workers",
)


def coefficient_of_variation(values):
    if not values:
        return 0.0
    mean = statistics.mean(values)
    return statistics.pstdev(values) / max(abs(mean), 1e-12)


def measured_features(pilot, pilot_count, remaining, total_count, workers):
    """Feature order is serialized with the model and checked when loading."""
    costs = [estimated_cost(task) for task in remaining]
    mean_cost = statistics.mean(costs) if costs else 0.0
    tail_count = max(1, len(costs) // 8)
    total_cost = sum(costs)
    return [
        pilot["mean_task_s"],
        coefficient_of_variation(pilot["service_s"]),
        pilot_count / max(pilot["elapsed_s"], 1e-12),
        percentile(pilot["queue_wait_s"], 95),
        percentile(pilot["batch_latencies_s"], 95),
        percentile(pilot["service_s"], 95),
        coefficient_of_variation(costs),
        max(costs, default=0.0) / max(mean_cost, 1e-12),
        sum(costs[-tail_count:]) / max(total_cost, 1e-12),
        sum(task.kernel == "prime" for task in remaining) / max(1, len(remaining)),
        len(remaining) / total_count,
        float(workers),
    ]


def _run_remainder(pool, remaining, workers, policy):
    if policy == "fixed_4":
        return _dispatch(pool, remaining, 4), math.ceil(len(remaining) / 4)
    count = int(policy.split("_")[1])
    batches = make_balanced_batches(remaining, workers, count)
    submitted_ns = time.perf_counter_ns()
    rows = pool.map(_batch, batches, chunksize=1)
    data = {
        "checksum": sum(row["checksum"] for row in rows),
        "batch_latencies_s": [(row["ended_ns"] - submitted_ns) / 1e9 for row in rows],
        "queue_wait_s": [max(0.0, (row["started_ns"] - submitted_ns) / 1e9) for row in rows],
        "service_s": [row["service_s"] for row in rows],
    }
    return data, len(batches)


def run_live(tasks, workers, model=None, forced_policy=None):
    """Run a trained decision or a forced candidate on the same pilot boundary.

    Forced runs supply training labels based on complete invocation times. A
    trained run makes the choice after observing its own completed pilot.
    """
    if not tasks or workers < 1:
        raise ValueError("nonempty tasks and workers >= 1 required")
    if forced_policy is None and model is None:
        raise ValueError("trained model or forced policy required")
    if forced_policy is not None and forced_policy not in POLICIES:
        raise ValueError(f"unknown forced policy: {forced_policy}")
    cpu_before = _cpu_seconds()
    start_ns = time.perf_counter_ns()
    pilot_count = min(len(tasks), 4 * workers * 4)
    with mp.Pool(workers) as pool:
        startup_s = (time.perf_counter_ns() - start_ns) / 1e9
        pilot = _dispatch(pool, tasks[:pilot_count], 4)
        remaining = tasks[pilot_count:]
        decision_ns = time.perf_counter_ns()
        features = measured_features(pilot, pilot_count, remaining, len(tasks), workers)
        policy = forced_policy if forced_policy is not None else model.predict_one(features)
        if policy not in POLICIES:
            raise ValueError(f"tree returned unsupported policy: {policy}")
        decision_s = (time.perf_counter_ns() - decision_ns) / 1e9
        checksum = pilot["checksum"]
        latencies = list(pilot["batch_latencies_s"])
        waits = list(pilot["queue_wait_s"])
        services = list(pilot["service_s"])
        batch_count = math.ceil(pilot_count / 4)
        if remaining:
            rest, rest_count = _run_remainder(pool, remaining, workers, policy)
            checksum += rest["checksum"]
            latencies.extend(rest["batch_latencies_s"])
            waits.extend(rest["queue_wait_s"])
            services.extend(rest["service_s"])
            batch_count += rest_count
    elapsed_s = (time.perf_counter_ns() - start_ns) / 1e9
    cpu_after = _cpu_seconds()
    cpu_s = max(0.0, cpu_after - cpu_before) if cpu_before is not None and cpu_after is not None else None
    return {
        "elapsed_s": elapsed_s, "checksum": checksum, "startup_s": startup_s,
        "cpu_s": cpu_s, "cpu_utilization_fraction": cpu_s / max(elapsed_s * workers, 1e-12) if cpu_s is not None else None,
        "batch_latency_p50_s": percentile(latencies, 50),
        "batch_latency_p95_s": percentile(latencies, 95),
        "batch_latency_p99_s": percentile(latencies, 99),
        "queue_wait_p95_s": percentile(waits, 95),
        "service_p95_s": percentile(services, 95),
        "decision_s": decision_s, "pilot_elapsed_s": pilot["elapsed_s"],
        "pilot_tasks": pilot_count, "batch_count": batch_count,
        "policy": policy, "features": dict(zip(FEATURES, features)),
        "pilot_boundary": "completed C work on first 4*workers*4 tasks; one barrier",
    }
