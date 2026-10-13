import unittest

from os_sched.scheduler_v2 import run
from os_sched.scheduler_v4 import run_balanced
from os_sched.straggler_workload import generate_tail_spike


class StragglerTests(unittest.TestCase):
    def test_reproducible_tail_spike(self):
        tasks, spike = generate_tail_spike(96, 5000, 4001, 20)
        self.assertEqual((tasks, spike), generate_tail_spike(96, 5000, 4001, 20))
        self.assertGreaterEqual(spike, 88)
        self.assertEqual(sum(t.work >= 5000 * 20 for t in tasks), 1)

    def test_balanced_and_fixed_outputs_match(self):
        tasks, _ = generate_tail_spike(96, 5000, 4002, 20)
        self.assertEqual(run_balanced(tasks, 2, 32)["checksum"],
                         run(tasks, 2, "fixed_4")["checksum"])


if __name__ == "__main__":
    unittest.main()
