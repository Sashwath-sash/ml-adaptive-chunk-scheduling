import unittest
from collections import Counter

from os_sched.experiment_v7 import FEATURES, feature_vector, run_learned
from os_sched.scheduler_v7 import POLICIES, plan_batches, run_policy
from os_sched.tree import DecisionTree
from os_sched.workload import generate


class LearnedPolicyTests(unittest.TestCase):
    def test_every_planner_preserves_tasks_exactly_once(self):
        tasks = generate("high", 83, 2000, 17)
        for policy in POLICIES:
            batches = plan_batches(tasks, policy)
            self.assertEqual(Counter(task for batch in batches for task in batch), Counter(tasks))
            self.assertTrue(all(batch for batch in batches))

    def test_learned_model_selects_policy_and_preserves_checksum(self):
        tasks = generate("moderate", 81, 1000, 19)
        model = DecisionTree().fit([[0.0] * len(FEATURES)], ["lpt_8"])
        chosen = run_learned(tasks, 2, model)
        baseline = run_policy(tasks, 2, "contig_32")
        self.assertEqual(chosen["selected_policy"], "lpt_8")
        self.assertEqual(chosen["checksum"], baseline["checksum"])
        self.assertGreater(chosen["inference_s"], 0)

    def test_features_respond_to_real_task_metadata(self):
        uniform = generate("uniform", 96, 1000, 3)
        high = generate("high", 96, 1000, 3)
        a, b = feature_vector(uniform, 2), feature_vector(high, 2)
        self.assertEqual(len(a), len(FEATURES))
        self.assertGreater(b[FEATURES.index("cost_cv")], a[FEATURES.index("cost_cv")])

    def test_invalid_policy_rejected(self):
        tasks = generate("uniform", 8, 100, 3)
        with self.assertRaises(ValueError):
            plan_batches(tasks, "magic")
        with self.assertRaises(ValueError):
            run_policy(tasks, 0, "lpt_8")


if __name__ == "__main__":
    unittest.main()
