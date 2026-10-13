import unittest

from os_sched.scheduler_v2 import run
from os_sched.scheduler_v4 import estimated_cost, make_balanced_batches, run_balanced
from os_sched.workload import generate


class BalancedTests(unittest.TestCase):
    def test_partition_preserves_every_task_once(self):
        tasks = generate("high", 96, 5000, 77)
        batches = make_balanced_batches(tasks, 2, 16)
        self.assertEqual(sorted(task.seed for batch in batches for task in batch),
                         sorted(task.seed for task in tasks))
        self.assertTrue(all(1 <= len(batch) <= 32 for batch in batches))
        costs = [sum(estimated_cost(task) for task in batch) for batch in batches]
        self.assertEqual(costs, sorted(costs, reverse=True))

    def test_balanced_matches_fixed_checksums(self):
        for kind, base in (("high", 5000), ("prime_scan", 50)):
            with self.subTest(kind=kind):
                tasks = generate(kind, 96, base, 78)
                self.assertEqual(run_balanced(tasks, 2, 16)["checksum"],
                                 run(tasks, 2, "fixed_4")["checksum"])


if __name__ == "__main__":
    unittest.main()
