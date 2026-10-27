"""Verify and show the frozen native ML cache admission system."""
import argparse
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument("--live", choices=("scripted", "llm", "nasa_aug", "calgary"))
args = ap.parse_args()

subprocess.run(["python", "verify_three_source.py"], cwd=ROOT, check=True)
subprocess.run(["python", "verify_hybrid_evidence.py"], cwd=ROOT, check=True)
reference = json.loads((ROOT / "results_hybrid_arc_probe.json").read_text())
native = json.loads((ROOT / "results_hybrid_native.json").read_text())
baselines = {"scripted": "results_three_source_scripted_3runs",
             "llm": "results_three_source_llm_3runs",
             "nasa_aug": "results_nasa_aug_three_source_3runs",
             "calgary": "results_calgary_baselines_3runs"}
print("\nHeld-out direct reads; all data checksums verified in native tests")
print(f"{'Stream':<14}{'Requests':>10}{'ARC':>10}{'ML ARC':>10}{'S3':>10}{'ML S3':>10}")
for name in baselines:
    base = json.loads((ROOT / baselines[name] / "results.json").read_text())
    row = reference[name]
    assert base["requests"] == row["requests"]
    assert native[name]["arc"]["direct_reads"] == row["arc"]
    assert native[name]["hybrid_arc"]["direct_reads"] == row["hybrid_arc_ml"]
    assert native[name]["hybrid_s3fifo"]["direct_reads"] == row["hybrid_s3fifo_ml"]
    assert base["summary"]["s3fifo"]["direct_reads"] == row["s3fifo"]
    assert len({x["checksum"] for x in native[name].values()}) == 1
    label = {"scripted": "BrowseTrace A", "llm": "BrowseTrace B",
             "nasa_aug": "NASA August", "calgary": "Calgary"}[name]
    print(f"{label:<14}{row['requests']:>10,}{row['arc']:>10,}"
          f"{row['hybrid_arc_ml']:>10,}{row['s3fifo']:>10,}"
          f"{row['hybrid_s3fifo_ml']:>10,}")
print("\nML lowers direct-read counts relative to each parent policy; timing is workload-dependent.")

if args.live:
    folder = {"scripted": "cache_native_input_three_source_scripted",
              "llm": "cache_native_input_three_source_llm",
              "nasa_aug": "cache_native_input_nasa_aug_v1",
              "calgary": "cache_native_input_calgary_v1"}[args.live]
    linux_root = "/mnt/" + ROOT.drive[0].lower() + ROOT.as_posix()[2:]
    prefix = ["wsl.exe", "--cd", linux_root, "-e"]
    subprocess.run(prefix + ["gcc", "-O3", "-std=c11", "-Wall", "-Wextra",
                             "cache_native.c", "-lm", "-o", "cache_native"], check=True)
    print(f"\nFresh Linux O_DIRECT replay: {args.live}", flush=True)
    checksums = set()
    for policy in ("arc", "hybrid_arc", "s3fifo", "hybrid_s3fifo"):
        command = prefix + ["./cache_native", f"{folder}/test_trace.txt",
                            f"{folder}/model.txt", "1", policy, "--sync"]
        process = subprocess.run(command, input="\n", text=True, capture_output=True)
        if process.returncode:
            raise RuntimeError(f"{policy}: {process.stderr}")
        record = json.loads(process.stdout.split("\n", 1)[1])["repeats"][0][0]
        checksums.add(record["checksum"])
        assert record["direct_reads"] == {
            "arc": reference[args.live]["arc"],
            "hybrid_arc": reference[args.live]["hybrid_arc_ml"],
            "s3fifo": reference[args.live]["s3fifo"],
            "hybrid_s3fifo": reference[args.live]["hybrid_s3fifo_ml"]}[policy]
        print(f"{policy:<14} reads={record['direct_reads']:,} "
              f"loop={record['wall_seconds']:.3f}s checksum={record['checksum']}", flush=True)
    assert len(checksums) == 1
