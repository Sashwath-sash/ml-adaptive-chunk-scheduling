"""Audit the measured individual-task cost-model ablation."""
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path

from .cost_model_v8 import CostPredictor, fit_kernel, read_csv
from .scheduler_v2 import _one
from .scheduler_v4 import estimated_cost
from .workload import Task


def verify(folder=Path("results_cost_model_v8")):
    train = read_csv(folder / "train_tasks.csv")
    validation = read_csv(folder / "validation_tasks.csv")
    scores = read_csv(folder / "validation_accuracy.csv")
    artifact = json.loads((folder / "model.json").read_text(encoding="utf-8"))
    assert len(train) == artifact["train_rows"] == 9216
    assert len(validation) == artifact["validation_rows"] == 3456
    assert set(artifact["train_seeds"]).isdisjoint(artifact["validation_seeds"])
    assert {row["kernel"] for row in train} == {"synthetic", "prime"}
    for row in train + validation:
        assert float(row["service_s"]) > 0
        assert int(row["work"]) > 0
    for kernel, saved in artifact["coefficients"].items():
        recalculated = fit_kernel([row for row in train if row["kernel"] == kernel], artifact["ridge"])
        assert all(math.isclose(x, y, rel_tol=1e-10, abs_tol=1e-10) for x, y in zip(saved, recalculated))
    grouped = defaultdict(list)
    for row in validation:
        grouped[(row["kind"], row["seed"])].append(row)
    assert len(grouped) == len(scores) == 18
    predictor = CostPredictor(artifact["coefficients"])
    lookup = {(row["kind"], row["seed"]): row for row in scores}
    for key, rows in grouped.items():
        assert len(rows) == 192
        actual = [float(row["service_s"]) for row in rows]
        tasks = [Task(int(row["work"]), int(row["task_seed"]), row["kernel"]) for row in rows]
        analytic = [estimated_cost(task) for task in tasks]
        learned = [predictor.predict(task) for task in tasks]
        for name, estimates in (("analytic", analytic), ("learned", learned)):
            scale = statistics.median(actual) / statistics.median(estimates)
            error = statistics.median(abs(math.log(max(1e-12, estimate * scale) / observed))
                                      for estimate, observed in zip(estimates, actual))
            saved = float(lookup[key][f"{name}_median_absolute_log_error"])
            assert math.isclose(error, saved, rel_tol=1e-12, abs_tol=1e-12)
        # Re-execute two real C tasks in each validation group to check that
        # the saved task inputs and outputs correspond to the current kernel.
        for row, task in ((rows[0], tasks[0]), (rows[-1], tasks[-1])):
            assert int(row["checksum"]) == _one(task)
    print(f"PASS cost-model ablation: {len(train)} training tasks, {len(validation)} validation tasks, "
          "coefficients and prediction errors recomputed; sample C checksums equal")


if __name__ == "__main__":
    verify()
