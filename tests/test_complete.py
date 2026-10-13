import unittest

from os_sched.scheduler_v2 import CHUNKS, collect_training_row, run
from os_sched.tree import DecisionTree
from os_sched.workload import generate


class CompleteProjectTests(unittest.TestCase):
    def test_prime_workload_deterministic_and_checksums(self):
        tasks = generate("prime_scan", 96, 50, 201)
        self.assertEqual(tasks, generate("prime_scan", 96, 50, 201))
        a = run(tasks, 2, "sequential")
        b = run(tasks, 2, "fixed_4")
        self.assertEqual(a["checksum"], b["checksum"])
        self.assertGreater(a["checksum"], 0)

    def test_training_features_match_pilot_boundary(self):
        tasks = generate("phase_shift", 128, 5000, 19)
        features, label, times = collect_training_row(tasks, 2, 4, 1, 19)
        self.assertEqual(features[3], 4)
        self.assertEqual(features[4], (128 - 16) / 128)
        self.assertIn(label, CHUNKS)
        self.assertEqual(set(times), set(CHUNKS))
        self.assertTrue(all(value > 0 for value in times.values()))

    def test_online_tree_decisions_and_latency_metrics(self):
        tasks = generate("phase_shift", 96, 5000, 29)
        model = DecisionTree(max_depth=1, min_leaf=1).fit([[0], [1]], [4, 16])
        events = []
        result = run(tasks, 2, "guarded_ml", model, events.append)
        self.assertEqual(len(events), len(result["decisions"]))
        self.assertEqual(sum(e["tasks_completed"] for e in events), len(tasks))
        self.assertTrue(all(1 <= e["new_chunk"] <= 64 for e in events))
        self.assertGreater(result["batch_latency_p95_s"], 0)
        self.assertGreaterEqual(result["decision_p95_s"], 0)
        self.assertEqual(result["checksum"], run(tasks, 2, "fixed_4")["checksum"])


if __name__ == "__main__":
    unittest.main()
