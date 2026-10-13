"""Low-barrier adaptive dispatch: one measured pilot, then one bulk dispatch.

This keeps the saved tree and the online feature boundary used for training,
but avoids the repeated stop-and-wait rounds of scheduler_v2.
"""
import multiprocessing as mp
import time

from .scheduler_v2 import _cpu_seconds, _dispatch, percentile


def run_once(tasks, workers, model, on_decision=None):
    if not tasks or workers < 1 or model is None:
        raise ValueError("nonempty tasks, workers >= 1 and a trained model required")
    cpu_before = _cpu_seconds()
    started_ns = time.perf_counter_ns()
    pilot_count = min(len(tasks), 4 * workers * 2)
    batches, waits, services = [], [], []
    with mp.Pool(workers) as pool:
        startup_s = (time.perf_counter_ns() - started_ns) / 1e9
        pilot = _dispatch(pool, tasks[:pilot_count], 4)
        batches.extend(pilot["batch_latencies_s"])
        waits.extend(pilot["queue_wait_s"])
        services.extend(pilot["service_s"])
        remaining = tasks[pilot_count:]
        decision_started = time.perf_counter_ns()
        features = [pilot["mean_task_s"], pilot["spread"],
                    pilot_count / max(pilot["elapsed_s"], 1e-12), 4.0,
                    len(remaining) / len(tasks)]
        chunk = min(64, max(1, int(model.predict_one(features))))
        decision_s = (time.perf_counter_ns() - decision_started) / 1e9
        event = {"round": 1, "old_chunk": 4, "new_chunk": chunk,
                 "tasks_completed": pilot_count, "round_s": pilot["elapsed_s"],
                 "throughput": features[2], "batch_spread": pilot["spread"],
                 "mean_task_s": pilot["mean_task_s"], "throughput_change": 0.0,
                 "task_cost_change": 0.0, "decision_s": decision_s,
                 "remaining_tasks": len(remaining), "reason": "tree_once"}
        if on_decision:
            on_decision(event)
        checksum = pilot["checksum"]
        if remaining:
            bulk = _dispatch(pool, remaining, chunk)
            checksum += bulk["checksum"]
            batches.extend(bulk["batch_latencies_s"])
            waits.extend(bulk["queue_wait_s"])
            services.extend(bulk["service_s"])
    elapsed_s = (time.perf_counter_ns() - started_ns) / 1e9
    cpu_after = _cpu_seconds()
    cpu_s = max(0.0, cpu_after - cpu_before) if cpu_before is not None and cpu_after is not None else None
    return {"elapsed_s": elapsed_s, "checksum": checksum, "decisions": [event],
            "startup_s": startup_s, "cpu_s": cpu_s,
            "cpu_utilization_fraction": cpu_s / max(elapsed_s * workers, 1e-12) if cpu_s is not None else None,
            "batch_latency_p50_s": percentile(batches, 50),
            "batch_latency_p95_s": percentile(batches, 95),
            "batch_latency_p99_s": percentile(batches, 99),
            "queue_wait_p95_s": percentile(waits, 95),
            "service_p95_s": percentile(services, 95),
            "decision_p95_s": decision_s}
