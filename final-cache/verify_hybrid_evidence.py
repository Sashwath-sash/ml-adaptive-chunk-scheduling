"""Check the saved hybrid policy evidence, hashes, and checksums."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
offline = json.loads((ROOT / "results_hybrid_arc_probe.json").read_text())
native = json.loads((ROOT / "results_hybrid_native.json").read_text())
arc_time = json.loads((ROOT / "results_hybrid_native_benchmark.json").read_text())
arc_calgary = json.loads((ROOT / "results_calgary_hybrid_arc_5runs.json").read_text())
s3_time = json.loads((ROOT / "results_hybrid_s3_native_benchmark.json").read_text())
expected = {
    "scripted": (7430, 7104, 7773, 7336),
    "llm": (17913, 17740, 18950, 18586),
    "nasa_aug": (8792, 8130, 8349, 8048),
    "calgary": (16493, 15718, 15406, 15177),
}
for name, values in expected.items():
    assert tuple(offline[name][key] for key in
                 ("arc", "hybrid_arc_ml", "s3fifo", "hybrid_s3fifo_ml")) == values
    assert tuple(native[name][key]["direct_reads"] for key in
                 ("arc", "hybrid_arc", "hybrid_s3fifo")) == (values[0], values[1], values[3])
    assert len({entry["checksum"] for entry in native[name].values()}) == 1
    a = arc_calgary[name] if name == "calgary" else arc_time[name]
    s = s3_time[name]
    for records, baseline, hybrid in ((a, "arc", "hybrid_arc"),
                                      (s, "s3fifo", "hybrid_s3fifo")):
        assert len(records[baseline]["raw_runs"]) == 5
        assert len(records[hybrid]["raw_runs"]) == 5
        assert records[baseline]["direct_reads"] == values[0 if baseline == "arc" else 2]
        assert records[hybrid]["direct_reads"] == values[1 if baseline == "arc" else 3]
        assert len({r["checksum"] for policy in (baseline, hybrid)
                    for r in records[policy]["raw_runs"]}) == 1
calgary = json.loads((ROOT / "data/calgary_last_100k_manifest.json").read_text())
assert hashlib.sha256((ROOT / "data/calgary_last_100k_cache.csv").read_bytes()).hexdigest() == calgary["derived_sha256"]
quota = json.loads((ROOT / "results_quota_probe.json").read_text())
assert quota["summary"]["ml"]["test_selected_total_misses"] == 24118
assert quota["summary"]["two_queue"]["test_selected_total_misses"] == 24285
print("PASS: hybrid counts, model/policy checksums, five-run timing records, external-source hash, negative quota probe")
