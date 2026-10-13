import ctypes
import multiprocessing as mp
import statistics
import time
from pathlib import Path

from .tree import DecisionTree

_kernel = None
_LIB = Path(__file__).resolve().parents[1] / "build" / "libwork_kernel.so"
CHUNKS = (1, 4, 16, 64)


def _load_kernel():
    global _kernel
    if _kernel is None:
        if not _LIB.exists():
            raise FileNotFoundError(f"compile the C kernel first: {_LIB}")
        lib = ctypes.CDLL(str(_LIB))
        lib.cpu_work.argtypes = (ctypes.c_uint64, ctypes.c_uint64)
        lib.cpu_work.restype = ctypes.c_uint64
        _kernel = lib.cpu_work
    return _kernel


def _one(task):
    return int(_load_kernel()(task.work, task.seed))


def _batch(batch):
    start = time.perf_counter()
    checksum = sum(_one(task) for task in batch)
    return len(batch), time.perf_counter() - start, checksum


def _batches(tasks, chunk):
    return [tasks[i:i + chunk] for i in range(0, len(tasks), chunk)]


def _round(pool, tasks, chunk, workers):
    limit = chunk * workers * 2
    selected = tasks[:limit]
    start = time.perf_counter()
    results = pool.map(_batch, _batches(selected, chunk), chunksize=1)
    elapsed = time.perf_counter() - start
    durations = [x[1] for x in results]
    spread = 0.0 if len(durations) < 2 else (max(durations) - min(durations)) / max(max(durations), 1e-12)
    return selected, elapsed, sum(x[2] for x in results), spread, sum(durations) / len(selected)


def run(tasks, workers, method, model=None):
    if method not in {"sequential", "fixed_1", "fixed_4", "fixed_16", "fixed_64", "rule", "ml", "guarded_ml"}:
        raise ValueError(method)
    started = time.perf_counter()
    if method == "sequential":
        return _sequential(tasks, started)
    if method.startswith("fixed_"):
        chunk = int(method.split("_")[1])
        with mp.Pool(workers) as pool:
            checksum = sum(pool.map(_one, tasks, chunksize=chunk))
        return {"elapsed_s": time.perf_counter() - started, "checksum": checksum, "decisions": []}
    if method in {"ml", "guarded_ml"} and model is None:
        raise ValueError("trained model required")
    current = 4
    remaining = list(tasks)
    checksum = 0
    decisions = []
    previous_throughput = None
    with mp.Pool(workers) as pool:
        while remaining:
            selected, elapsed, part_checksum, spread, mean_task_s = _round(pool, remaining, current, workers)
            remaining = remaining[len(selected):]
            checksum += part_checksum
            throughput = len(selected) / max(elapsed, 1e-12)
            relative_change = 0.0 if previous_throughput is None else throughput / max(previous_throughput, 1e-12) - 1
            features = [mean_task_s, spread, throughput, float(current), len(remaining) / max(len(tasks), 1)]
            chosen = current
            reason = "hold"
            if method == "rule":
                if previous_throughput is not None and (relative_change < -0.08 or spread >= 0.30):
                    chosen, reason = max(1, current // 2), "rule_decrease"
                elif previous_throughput is not None and relative_change > 0.08:
                    chosen, reason = min(64, current * 2), "rule_increase"
            else:
                chosen, reason = int(model.predict_one(features)), "tree"
                if method == "guarded_ml" and previous_throughput is not None and relative_change < -0.25:
                    chosen, reason = max(1, current // 2), "throughput_guard"
            chosen = min(64, max(1, chosen))
            decisions.append({"round": len(decisions) + 1, "old_chunk": current, "new_chunk": chosen,
                              "tasks_completed": len(selected), "round_s": elapsed, "throughput": throughput,
                              "batch_spread": spread, "mean_task_s": mean_task_s,
                              "relative_throughput_change": relative_change, "reason": reason})
            current = chosen
            previous_throughput = throughput
    assert sum(d["tasks_completed"] for d in decisions) == len(tasks)
    return {"elapsed_s": time.perf_counter() - started, "checksum": checksum, "decisions": decisions}


def _sequential(tasks, started):
    checksum = sum(_one(t) for t in tasks)
    return {"elapsed_s": time.perf_counter() - started, "checksum": checksum, "decisions": []}


def collect_training_row(tasks, workers):
    """Measure pilot features, then label a separate window by actual candidate times."""
    if len(tasks) < 96:
        raise ValueError("at least 96 tasks required")
    with mp.Pool(workers) as pool:
        pilot = tasks[:32]
        selected, elapsed, _, spread, mean_task_s = _round(pool, pilot, 4, workers)
        features = [mean_task_s, spread, len(selected) / max(elapsed, 1e-12), 4.0, 64 / len(tasks)]
        target = tasks[32:96]
        timings = {}
        for chunk in CHUNKS:
            start = time.perf_counter()
            pool.map(_batch, _batches(target, chunk), chunksize=1)
            timings[chunk] = time.perf_counter() - start
    best = min(timings, key=timings.get)
    return features, best, timings
