"""Predict individual C-task service costs, then LPT-pack before dispatch."""
import heapq
import multiprocessing as mp
import time

from .experiment_v7 import feature_vector
from .scheduler_v2 import _batch, _cpu_seconds, percentile


def pack_predicted(tasks, predicted_costs, target_batches):
    if not tasks or len(tasks) != len(predicted_costs) or target_batches < 1:
        raise ValueError("tasks, predictions, and target_batches must be valid")
    if any(cost <= 0 for cost in predicted_costs):
        raise ValueError("all predicted costs must be positive")
    count = min(target_batches, len(tasks))
    bins = [[] for _ in range(count)]
    heap = [(0.0, index) for index in range(count)]
    heapq.heapify(heap)
    for task, cost in sorted(zip(tasks, predicted_costs), key=lambda pair: pair[1], reverse=True):
        load, index = heapq.heappop(heap)
        bins[index].append(task)
        heapq.heappush(heap, (load + cost, index))
    loads_by_index = {index: load for load, index in heap}
    batches = [bins[index] for index in sorted(range(count), key=lambda i: loads_by_index[i], reverse=True)
               if bins[index]]
    assert sum(map(len, batches)) == len(tasks)
    return batches


def run_ml(tasks, workers, cost_model, policy_model=None, fixed_bins=2):
    if workers < 1 or not tasks:
        raise ValueError("workers >= 1 and nonempty tasks required")
    cpu_before = _cpu_seconds()
    started_ns = time.perf_counter_ns()
    policy = f"lpt_{fixed_bins}"
    if policy_model is not None:
        features = feature_vector(tasks, workers)
        policy = policy_model.predict_one(features)
        if policy not in ("lpt_2", "lpt_4", "lpt_8"):
            raise ValueError(f"policy model chose unsupported predicted-cost policy: {policy}")
    predicted = [cost_model.predict(task) for task in tasks]
    prediction_s = (time.perf_counter_ns() - started_ns) / 1e9
    batches = pack_predicted(tasks, predicted, int(policy.split("_")[1]))
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
    return {"elapsed_s": elapsed_s, "checksum": sum(row["checksum"] for row in rows),
            "selected_policy": policy, "prediction_s": prediction_s,
            "planning_s": planning_s, "startup_s": startup_s,
            "cpu_s": cpu_s, "cpu_utilization_fraction": cpu_s / max(elapsed_s * workers, 1e-12) if cpu_s is not None else None,
            "batch_latency_p95_s": percentile(latencies, 95),
            "queue_wait_p95_s": percentile(waits, 95),
            "service_p95_s": percentile([row["service_s"] for row in rows], 95),
            "batch_count": len(batches)}
