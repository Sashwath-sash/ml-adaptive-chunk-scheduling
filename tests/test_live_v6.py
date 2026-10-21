import unittest

from os_sched.scheduler_v2 import run
from os_sched.scheduler_v6 import FEATURES, POLICIES, run_live
from os_sched.tree import DecisionTree
from os_sched.workload import generate


class LiveTreeTests(unittest.TestCase):
    def test_real_pilot_features_and_equal_output(self):
        tasks = generate("high", 96, 6000, 71)
        baseline = run(tasks, 2, "fixed_4")
        results = {policy: run_live(tasks, 2, forced_policy=policy) for policy in POLICIES}
        self.assertEqual({row["checksum"] for row in results.values()}, {baseline["checksum"]})
        for result in results.values():
            self.assertEqual(result["pilot_tasks"], 32)
            self.assertEqual(set(result["features"]), set(FEATURES))
            self.assertGreater(result["features"]["pilot_mean_task_s"], 0)
            self.assertGreater(result["features"]["pilot_throughput_tps"], 0)
            self.assertGreaterEqual(result["features"]["pilot_queue_wait_p95_s"], 0)
            self.assertGreater(result["elapsed_s"], result["pilot_elapsed_s"])

    def test_trained_tree_is_used_after_pilot(self):
        tasks = generate("prime_scan", 96, 50, 73)
        model = DecisionTree().fit([[0.0] * len(FEATURES)], ["cost_32"])
        result = run_live(tasks, 2, model=model)
        self.assertEqual(result["policy"], "cost_32")
        self.assertEqual(result["checksum"], run(tasks, 2, "fixed_4")["checksum"])
        self.assertGreater(result["decision_s"], 0)

    def test_model_or_forced_policy_required(self):
        tasks = generate("uniform", 16, 100, 1)
        with self.assertRaises(ValueError):
            run_live(tasks, 2)
        with self.assertRaises(ValueError):
            run_live(tasks, 2, forced_policy="made_up")

    def test_short_input_without_remainder(self):
        tasks = generate("moderate", 7, 1000, 11)
        baseline = run(tasks, 1, "fixed_4")
        for policy in POLICIES:
            result = run_live(tasks, 1, forced_policy=policy)
            self.assertEqual(result["checksum"], baseline["checksum"])
            self.assertEqual(result["pilot_tasks"], 7)
            self.assertEqual(result["batch_count"], 2)

    def test_four_workers_irregular_count(self):
        tasks = generate("high", 81, 2000, 19)
        baseline = run(tasks, 4, "fixed_4")
        for policy in POLICIES:
            result = run_live(tasks, 4, forced_policy=policy)
            self.assertEqual(result["checksum"], baseline["checksum"])
            self.assertEqual(result["pilot_tasks"], 64)
            self.assertGreater(result["batch_count"], 16)


if __name__ == "__main__":
    unittest.main()
