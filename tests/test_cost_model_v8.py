import unittest
from collections import Counter

from os_sched.scheduler_v7 import run_policy
from os_sched.scheduler_v8 import pack_predicted, run_ml
from os_sched.workload import generate


class FakeCostModel:
    def predict(self, task):
        return float(task.work)


class PredictedCostTests(unittest.TestCase):
    def test_packing_preserves_every_task(self):
        tasks = generate("high", 83, 1000, 1)
        costs = [float(task.work) for task in tasks]
        for bins in (2, 4, 8):
            groups = pack_predicted(tasks, costs, bins)
            self.assertEqual(Counter(task for group in groups for task in group), Counter(tasks))
            self.assertEqual(len(groups), bins)

    def test_runtime_predictions_drive_real_execution(self):
        tasks = generate("moderate", 81, 2000, 2)
        predicted = run_ml(tasks, 2, FakeCostModel(), fixed_bins=2)
        analytic = run_policy(tasks, 2, "lpt_2")
        self.assertEqual(predicted["checksum"], analytic["checksum"])
        self.assertEqual(predicted["batch_count"], 2)
        self.assertGreater(predicted["prediction_s"], 0)


if __name__ == "__main__":
    unittest.main()
