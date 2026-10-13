import unittest

from os_sched.scheduler import CHUNKS, collect_training_row, run
from os_sched.tree import DecisionTree
from os_sched.workload import generate


class ProjectTests(unittest.TestCase):
    def test_generator_reproducible_and_phase_shifted(self):
        a = generate("phase_shift", 96, 5000, 7)
        self.assertEqual(a, generate("phase_shift", 96, 5000, 7))
        self.assertNotEqual([x.work for x in a[:48]], [x.work for x in a[48:]])

    def test_tree_learns_simple_split_and_serializes(self):
        x = [[float(i)] for i in range(10)]
        y = [1] * 5 + [4] * 5
        model = DecisionTree(max_depth=2, min_leaf=2).fit(x, y)
        self.assertEqual(model.predict_one([0]), 1)
        self.assertEqual(model.predict_one([9]), 4)
        self.assertEqual(DecisionTree.from_dict(model.to_dict()).predict_one([9]), 4)

    def test_all_methods_compute_same_result(self):
        tasks = generate("phase_shift", 96, 2000, 17)
        train_x, label, _ = collect_training_row(tasks, 2)
        model = DecisionTree(max_depth=1, min_leaf=1).fit([train_x, [x * 1.1 for x in train_x]], [label, 4])
        checksum = run(tasks, 2, "sequential")["checksum"]
        for method in ("fixed_1", "fixed_4", "fixed_16", "fixed_64", "rule", "ml", "guarded_ml"):
            result = run(tasks, 2, method, model)
            self.assertEqual(result["checksum"], checksum, method)
            self.assertGreater(result["elapsed_s"], 0)
            if method in {"rule", "ml", "guarded_ml"}:
                self.assertEqual(sum(x["tasks_completed"] for x in result["decisions"]), len(tasks))


if __name__ == "__main__":
    unittest.main()
