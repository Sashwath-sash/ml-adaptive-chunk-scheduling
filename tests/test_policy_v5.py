import unittest

from os_sched.experiment_v5 import label_for
from os_sched.scheduler_v2 import run
from os_sched.scheduler_v5 import FEATURES, POLICIES, run_auto, run_hybrid_once, task_features
from os_sched.straggler_workload import generate_tail_spike
from os_sched.tree import DecisionTree
from os_sched.workload import generate


class PolicyV5Tests(unittest.TestCase):
    def setUp(self):
        self.chunk_model = DecisionTree().fit([[0.0] * 5], [4])
        self.selector = DecisionTree().fit([[0.0] * len(FEATURES)], ["balanced_32"])

    def test_features_are_pre_dispatch_and_tail_sensitive(self):
        uniform = generate("uniform", 96, 5000, 12)
        late, _ = generate_tail_spike(96, 5000, 12, 40)
        a, b = task_features(uniform, 2), task_features(late, 2)
        self.assertEqual(len(a), len(FEATURES))
        self.assertEqual(a[-1], 2.0)
        self.assertGreater(b[3], a[3])
        self.assertGreater(b[2], a[2])
        self.assertGreater(b[5], 0.875)
        self.assertEqual(task_features(uniform, 2), task_features(uniform, 2))

    def test_hybrid_and_auto_preserve_all_work(self):
        for kind, base in (("high", 4000), ("prime_scan", 40)):
            with self.subTest(kind=kind):
                tasks = generate(kind, 96, base, 42)
                expected = run(tasks, 2, "fixed_4")["checksum"]
                hybrid = run_hybrid_once(tasks, 2, self.chunk_model)
                auto = run_auto(tasks, 2, self.selector, self.chunk_model)
                self.assertEqual(hybrid["checksum"], expected)
                self.assertEqual(auto["checksum"], expected)
                self.assertEqual(auto["selected_policy"], "balanced_32")
                self.assertGreaterEqual(auto["elapsed_s"], auto["feature_s"] + auto["selection_s"])

    def test_label_margin_favors_fixed_on_close_results(self):
        values = dict.fromkeys(POLICIES, 1.1)
        values.update(fixed_4=1.0, balanced_32=0.97)
        self.assertEqual(label_for(values, 0.05), "fixed_4")
        values["balanced_32"] = 0.90
        self.assertEqual(label_for(values, 0.05), "balanced_32")

    def test_invalid_inputs_rejected(self):
        with self.assertRaises(ValueError):
            task_features([], 2)
        with self.assertRaises(ValueError):
            run_hybrid_once(generate("uniform", 16, 100, 1), 0, self.chunk_model)


if __name__ == "__main__":
    unittest.main()
