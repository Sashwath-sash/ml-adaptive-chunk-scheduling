"""Check saved controls, capacity study, and calibration provenance."""
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
names = {
    256: "results_admission_controls_256_2026-10-27.json",
    512: "results_admission_controls_2026-10-27.json",
    1024: "results_admission_controls_1024_2026-10-27.json",
}
selection = json.loads((ROOT / "results_admission_threshold_selection_2026-10-27.json").read_text())
calibrated = json.loads((ROOT / "results_selected_thresholds_2026-10-27.json").read_text())
assert calibrated["exploratory_post_hoc"] is True
assert set(selection["selection_splits"]) == {
    "BrowseTrace A val", "BrowseTrace B val", "NASA July val"}
fixed_wins = {}
calibrated_tally = [0, 0, 0]
for capacity, file in names.items():
    sweep = json.loads((ROOT / file).read_text())
    assert set(sweep["streams"]) == {
        "BrowseTrace A", "BrowseTrace B", "NASA August", "Calgary"}
    count = 0
    for stream, saved in sweep["streams"].items():
        policies = saved["policies"]
        assert len(policies) == 6
        for parent in ("arc", "s3fifo"):
            ml, cheap = "hybrid_" + parent, "second_touch_" + parent
            base = policies[parent]["direct_reads"]
            learned = policies[ml]["direct_reads"]
            assert policies[cheap]["tree_nodes_evaluated"] == 0
            assert policies[ml]["tree_nodes_evaluated"] > 0
            count += learned < base
            c = calibrated["capacities"][str(capacity)][stream][parent]
            assert (c["parent_direct_reads"], c["original_fixed_threshold_direct_reads"],
                    c["checksum"]) == (base, learned, saved["checksum"])
            threshold = selection["capacities"][str(capacity)][parent]["chosen"]["threshold"]
            assert c["threshold_selected_on_validation"] == threshold
            selected_reads = c["calibrated_direct_reads"]
            calibrated_tally[(selected_reads == base) + 2 * (selected_reads > base)] += 1
    fixed_wins[capacity] = count
assert fixed_wins == {256: 3, 512: 8, 1024: 4}
assert calibrated_tally == [18, 5, 1], calibrated_tally
meta = json.loads((ROOT / "results_metacdn_sample10_100k_512.json").read_text())
meta = meta["streams"]["MetaCDN-sampled"]
assert {p: d["direct_reads"] for p, d in meta["policies"].items()} == {
    "arc": 62532, "second_touch_arc": 69067, "hybrid_arc": 69720,
    "s3fifo": 61628, "second_touch_s3fifo": 68806,
    "hybrid_s3fifo": 69646}
diagnostics = json.loads((ROOT / "results_metacdn_sample10_diagnostics.json").read_text())
assert diagnostics["independent_reference_read_counts"] == {
    p: meta["policies"][p]["direct_reads"]
    for p in ("arc", "hybrid_arc", "s3fifo", "hybrid_s3fifo")}
assert 0.80 < diagnostics["roc_auc"] < 0.81
print("PASS: controls, checksums, capacity selection, and independent key-only stress counts")
