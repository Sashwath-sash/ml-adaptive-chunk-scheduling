"""Paired comparison against standard Python process-pool dispatch APIs."""
import argparse
import csv
import json
import multiprocessing as mp
import random
import statistics
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from .experiment_complete import KINDS, make_tasks, write_csv
from .scheduler_v2 import _one, run
from .tree import DecisionTree

PROJECT_METHODS = ("fixed_4", "fixed_16", "rule", "ml", "guarded_ml")
EXISTING_METHODS = ("pool_map_4", "pool_map_16", "imap_unordered_4", "imap_unordered_16",
                    "process_executor_4", "process_executor_16")
METHODS = PROJECT_METHODS + EXISTING_METHODS


def builtin(tasks, workers, method):
    started = time.perf_counter_ns()
    chunk = int(method.rsplit("_", 1)[1])
    if method.startswith("process_executor"):
        with ProcessPoolExecutor(max_workers=workers) as executor:
            checksum = sum(executor.map(_one, tasks, chunksize=chunk))
    else:
        with mp.Pool(workers) as pool:
            if method.startswith("pool_map"):
                checksum = sum(pool.map(_one, tasks, chunksize=chunk))
            else:
                checksum = sum(pool.imap_unordered(_one, tasks, chunksize=chunk))
    return {"elapsed_s": (time.perf_counter_ns() - started) / 1e9, "checksum": checksum}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--results",type=Path,default=Path("results_complete"))
    ap.add_argument("--workers",type=int,default=2)
    ap.add_argument("--base",type=int,default=1_500_000)
    ap.add_argument("--prime-base",type=int,default=3000)
    ap.add_argument("--count",type=int,default=192)
    ap.add_argument("--repeats",type=int,default=5)
    args=ap.parse_args()
    model=DecisionTree.from_dict(json.loads((args.results/"model.json").read_text(encoding="utf-8")))
    raw=[]
    groups=[(kind,repeat) for kind in KINDS for repeat in range(args.repeats)]
    random.Random(91021).shuffle(groups)
    for kind,repeat in groups:
        seed=1001+repeat
        tasks=make_tasks(kind,args.count,args.base,args.prime_base,seed)
        order=list(METHODS)
        random.Random(seed*97+len(kind)).shuffle(order)
        checksum=None
        for position,method in enumerate(order):
            result=run(tasks,args.workers,method,model) if method in PROJECT_METHODS else builtin(tasks,args.workers,method)
            if checksum is None:checksum=result["checksum"]
            if result["checksum"]!=checksum:raise AssertionError(f"checksum mismatch {kind} {repeat+1} {method}")
            raw.append({"workload":kind,"repeat":repeat+1,"seed":seed,"order":position,
                        "method":method,"elapsed_s":result["elapsed_s"],"checksum":result["checksum"]})
        print(f"COMPARED {kind:11s} repeat={repeat+1} methods={len(order)}",flush=True)
    write_csv(args.results/"existing_options_raw.csv",raw)
    summaries=[]
    for kind in KINDS:
        baseline={int(row["repeat"]):float(row["elapsed_s"]) for row in raw
                  if row["workload"]==kind and row["method"]=="fixed_4"}
        for method in METHODS:
            rows=[row for row in raw if row["workload"]==kind and row["method"]==method]
            times=[row["elapsed_s"] for row in rows]
            summaries.append({"workload":kind,"method":method,"runs":len(rows),
                              "median_elapsed_s":statistics.median(times),
                              "min_elapsed_s":min(times),"max_elapsed_s":max(times),
                              "median_ratio_to_paired_fixed4":statistics.median(row["elapsed_s"]/baseline[row["repeat"]] for row in rows)})
    write_csv(args.results/"existing_options_summary.csv",summaries)
    report={"status":"PASS","workloads":len(KINDS),"repeats":args.repeats,"methods":len(METHODS),
            "raw_rows":len(raw),"summary_rows":len(summaries),"checksums_equal_within_each_group":True,
            "comparison_scope":"same deterministic tasks and seeds; randomized method order; Python built-in APIs have different overhead paths",
            "method_definitions":{"pool_map_*":"multiprocessing.Pool.map(_one, chunksize=*)",
                                  "imap_unordered_*":"multiprocessing.Pool.imap_unordered(_one, chunksize=*)",
                                  "process_executor_*":"concurrent.futures.ProcessPoolExecutor.map(_one, chunksize=*)"}}
    (args.results/"existing_options_manifest.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    assert len(raw)==len(KINDS)*args.repeats*len(METHODS)
    print(f"DONE existing-option comparison: {len(raw)} timed runs, {len(summaries)} summaries",flush=True)


if __name__=="__main__":main()
