"""Measured online chunk scheduler for a Linux process pool.

This controls application-level dispatch to OS processes; it does not modify
the Linux kernel scheduler. Timed runs include worker startup and teardown.
"""
import ctypes
import multiprocessing as mp
import os
import statistics
import time
from pathlib import Path

CHUNKS = (1, 4, 16, 64)
METHODS = ("sequential", "fixed_1", "fixed_4", "fixed_16", "fixed_64", "rule", "ml", "guarded_ml")
_LIB = Path(__file__).resolve().parents[1] / "build" / ("work_kernel.dll" if os.name == "nt" else "libwork_kernel.so")
_functions = None


def _load_functions():
    global _functions
    if _functions is None:
        if not _LIB.exists():
            raise FileNotFoundError(f"compile the C kernel first: {_LIB}")
        library = ctypes.CDLL(str(_LIB))
        for name in ("cpu_work", "prime_count"):
            function = getattr(library, name)
            function.argtypes = (ctypes.c_uint64, ctypes.c_uint64)
            function.restype = ctypes.c_uint64
        _functions = (library.cpu_work, library.prime_count)
    return _functions


def _one(task):
    synthetic, prime = _load_functions()
    return int((prime if task.kernel == "prime" else synthetic)(task.work, task.seed))


def _batch(batch):
    started_ns = time.perf_counter_ns()
    checksum = sum(_one(task) for task in batch)
    ended_ns = time.perf_counter_ns()
    return {"count": len(batch), "checksum": checksum, "started_ns": started_ns,
            "ended_ns": ended_ns, "service_s": (ended_ns - started_ns) / 1e9}


def _batches(tasks, chunk):
    return [tasks[i:i + chunk] for i in range(0, len(tasks), chunk)]


def _dispatch(pool, tasks, chunk):
    submitted_ns = time.perf_counter_ns()
    results = pool.map(_batch, _batches(tasks, chunk), chunksize=1)
    elapsed_s = (time.perf_counter_ns() - submitted_ns) / 1e9
    latencies = [(r["ended_ns"] - submitted_ns) / 1e9 for r in results]
    services = [r["service_s"] for r in results]
    spread = 0.0 if len(services) < 2 else (max(services) - min(services)) / max(max(services), 1e-12)
    return {"elapsed_s": elapsed_s, "checksum": sum(r["checksum"] for r in results),
            "spread": spread, "mean_task_s": sum(services) / len(tasks),
            "batch_latencies_s": latencies,
            "queue_wait_s": [max(0.0, (r["started_ns"] - submitted_ns) / 1e9) for r in results],
            "service_s": services}


def percentile(values, percentile):
    if not values:
        return 0.0
    ordered = sorted(values)
    index = (len(ordered) - 1) * percentile / 100
    low = int(index)
    high = min(len(ordered) - 1, low + 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (index - low)


def _cpu_seconds():
    try:
        import resource
        children = resource.getrusage(resource.RUSAGE_CHILDREN)
        parent = resource.getrusage(resource.RUSAGE_SELF)
        return children.ru_utime + children.ru_stime + parent.ru_utime + parent.ru_stime
    except ImportError:
        return None


def run(tasks, workers, method, model=None, on_decision=None):
    if method not in METHODS:
        raise ValueError(method)
    if workers < 1 or not tasks:
        raise ValueError("workers >= 1 and nonempty tasks required")
    if method in {"ml", "guarded_ml"} and model is None:
        raise ValueError("trained model required")
    cpu_before = _cpu_seconds()
    started_ns = time.perf_counter_ns()
    checksum, decisions, batches, waits, services = 0, [], [], [], []
    startup_s = 0.0
    if method == "sequential":
        result = _batch(tasks)
        checksum = result["checksum"]
        batches = [result["service_s"]]
        services = [result["service_s"]]
    else:
        pool_start = time.perf_counter_ns()
        with mp.Pool(workers) as pool:
            startup_s = (time.perf_counter_ns() - pool_start) / 1e9
            if method.startswith("fixed_"):
                result = _dispatch(pool, tasks, int(method.split("_")[1]))
                checksum = result["checksum"]
                batches.extend(result["batch_latencies_s"])
                waits.extend(result["queue_wait_s"])
                services.extend(result["service_s"])
            else:
                current, previous_throughput, previous_mean_task_s = 4, None, None
                remaining = list(tasks)
                while remaining:
                    selected = remaining[:current * workers * 2]
                    remaining = remaining[len(selected):]
                    result = _dispatch(pool, selected, current)
                    checksum += result["checksum"]
                    batches.extend(result["batch_latencies_s"])
                    waits.extend(result["queue_wait_s"])
                    services.extend(result["service_s"])
                    throughput = len(selected) / max(result["elapsed_s"], 1e-12)
                    change = 0.0 if previous_throughput is None else throughput / max(previous_throughput, 1e-12) - 1
                    task_cost_change = 0.0 if previous_mean_task_s is None else result["mean_task_s"] / max(previous_mean_task_s, 1e-12) - 1
                    decision_started = time.perf_counter_ns()
                    features = [result["mean_task_s"], result["spread"], throughput,
                                float(current), len(remaining) / len(tasks)]
                    chosen, reason = current, "hold"
                    if method == "rule":
                        if previous_throughput is not None and (change < -0.08 or result["spread"] >= .30):
                            chosen, reason = max(1, current // 2), "rule_decrease"
                        elif previous_throughput is not None and change > .08:
                            chosen, reason = min(64, current * 2), "rule_increase"
                    else:
                        chosen, reason = int(model.predict_one(features)), "tree"
                        if method == "guarded_ml" and previous_mean_task_s is not None and task_cost_change > .25:
                            chosen, reason = max(1, current // 2), "cost_increase_guard"
                    chosen = min(64, max(1, chosen))
                    decision_s = (time.perf_counter_ns() - decision_started) / 1e9
                    event = {"round": len(decisions) + 1, "old_chunk": current, "new_chunk": chosen,
                             "tasks_completed": len(selected), "round_s": result["elapsed_s"],
                             "throughput": throughput, "batch_spread": result["spread"],
                             "mean_task_s": result["mean_task_s"], "throughput_change": change,
                             "task_cost_change": task_cost_change, "decision_s": decision_s,
                             "remaining_tasks": len(remaining), "reason": reason}
                    decisions.append(event)
                    if on_decision:
                        on_decision(event)
                    current, previous_throughput, previous_mean_task_s = chosen, throughput, result["mean_task_s"]
    elapsed_s = (time.perf_counter_ns() - started_ns) / 1e9
    cpu_after = _cpu_seconds()
    cpu_s = max(0.0, cpu_after - cpu_before) if cpu_before is not None and cpu_after is not None else None
    return {"elapsed_s": elapsed_s, "checksum": checksum, "decisions": decisions,
            "startup_s": startup_s, "cpu_s": cpu_s,
            "cpu_utilization_fraction": cpu_s / max(elapsed_s * (1 if method == "sequential" else workers), 1e-12) if cpu_s is not None else None,
            "batch_latency_p50_s": percentile(batches, 50),
            "batch_latency_p95_s": percentile(batches, 95),
            "batch_latency_p99_s": percentile(batches, 99),
            "queue_wait_p95_s": percentile(waits, 95),
            "service_p95_s": percentile(services, 95),
            "decision_p95_s": percentile([d["decision_s"] for d in decisions], 95)}


def collect_training_row(tasks, workers, current_chunk=4, candidate_repeats=2, seed=0):
    """Train on features measured at a live-equivalent dispatch boundary.

    Candidate order is randomized. All candidates run on the same next window;
    a tie within 3% selects the larger chunk to avoid needless dispatch work.
    """
    import random
    if len(tasks) < 96 or candidate_repeats < 1:
        raise ValueError("at least 96 tasks and one candidate repeat required")
    pilot_size = min(len(tasks) - 64, current_chunk * workers * 2)
    target = tasks[pilot_size:pilot_size + 64]
    timings = {c: [] for c in CHUNKS}
    with mp.Pool(workers) as pool:
        pilot = _dispatch(pool, tasks[:pilot_size], current_chunk)
        features = [pilot["mean_task_s"], pilot["spread"], pilot_size / max(pilot["elapsed_s"], 1e-12),
                    float(current_chunk), (len(tasks) - pilot_size) / len(tasks)]
        rng = random.Random(seed)
        for _ in range(candidate_repeats):
            order = list(CHUNKS)
            rng.shuffle(order)
            for chunk in order:
                timings[chunk].append(_dispatch(pool, target, chunk)["elapsed_s"])
    medians = {chunk: statistics.median(values) for chunk, values in timings.items()}
    fastest = min(medians.values())
    near_best = [chunk for chunk in CHUNKS if medians[chunk] <= fastest * 1.03]
    return features, max(near_best), medians
