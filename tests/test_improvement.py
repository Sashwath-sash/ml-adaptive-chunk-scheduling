import unittest

from os_sched.scheduler_v2 import run
from os_sched.scheduler_v3 import run_once
from os_sched.tree import DecisionTree
from os_sched.workload import generate


class ImprovementTests(unittest.TestCase):
    def test_one_decision_matches_fixed_checksum(self):
        tasks = generate("phase_shift", 96, 5000, 402)
        model = DecisionTree(max_depth=1, min_leaf=1).fit([[0], [1]], [4, 16])
        events = []
        improved = run_once(tasks, 2, model, events.append)
        fixed = run(tasks, 2, "fixed_4")
        self.assertEqual(improved["checksum"], fixed["checksum"])
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["tasks_completed"], 16)
        self.assertEqual(events[0]["remaining_tasks"], 80)
        self.assertEqual(events[0]["reason"], "tree_once")
        self.assertGreater(improved["batch_latency_p95_s"], 0)

    def test_rejects_missing_model(self):
        with self.assertRaises(ValueError):
            run_once(generate("uniform", 16, 5000, 1), 2, None)


if __name__ == "__main__":
    unittest.main()
