"""Verify three-source evidence without rerunning experiments."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
expect = {
    "scripted": ("results_three_source_scripted_3runs", 16491,
                 {"lru": 8793, "second_touch": 7543, "two_queue": 7655,
                  "s3fifo": 7773, "ml": 6827}),
    "llm": ("results_three_source_llm_3runs", 71557,
            {"lru": 19713, "second_touch": 19209, "two_queue": 18683,
             "s3fifo": 18950, "ml": 18501}),
    "nasa_aug": ("results_nasa_aug_three_source_3runs", 100000,
                 {"lru": 10000, "second_touch": 9656, "two_queue": 9670,
                  "s3fifo": 8349, "ml": 8270}),
}
for name, (folder, requests, reads) in expect.items():
    data = json.loads((ROOT / folder / "results.json").read_text())
    assert data["requests"] == requests
    assert len(data["repeats"]) == 3
    for run in data["repeats"]:
        assert len(run) == 5
        assert len({item["checksum"] for item in run}) == 1
        assert {item["policy"]: item["direct_reads"] for item in run} == reads
    assert {policy: item["direct_reads"] for policy, item in data["summary"].items()} == reads
for name in ("nasa_jul_last_300k", "nasa_aug_last_100k"):
    path = ROOT / "data" / f"{name}_cache.csv"
    manifest = json.loads((ROOT / "data" / f"{name}_manifest.json").read_text())
    assert hashlib.sha256(path.read_bytes()).hexdigest() == manifest["derived_sha256"]
model = json.loads((ROOT / "results_cache_three_source_v1" / "results.json").read_text())
assert model["chosen"]["stages"] == 100
assert model["chosen"]["threshold"] == .2
assert model["train_val_counts"] == {"scripted": [49473, 16491],
                                     "llm": [214669, 71556],
                                     "nasa_july": [150000, 50000]}
sharded = json.loads((ROOT / "results_nasa_aug_sharded_3runs" / "results.json").read_text())
assert sharded["sharded"] and sharded["workers"] == 2 and sharded["repeats"] == 3
assert {p: x["sum_direct_reads_per_batch"] for p, x in sharded["summary"].items()} == {
    "lru": 10458, "second_touch": 10137, "two_queue": 10174,
    "s3fifo": 8977, "ml": 8860}
for run in sharded["runs"]:
    assert run["sum_direct_reads"] == sum(x["direct_reads"] for x in run["workers_detail"])
arc = json.loads((ROOT / "results_arc_probe.json").read_text())
assert {name: item["arc_direct_reads"] for name, item in arc.items()} == {
    "scripted": 7430, "llm": 17913, "nasa_aug": 8792}
print("PASS: three-source held-outs, source hashes, frozen settings, checksums, concurrent totals")
