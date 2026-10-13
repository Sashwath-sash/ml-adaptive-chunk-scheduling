# Balanced batching selection recorded before fresh test

Development benchmark: deterministic seeds **201–203**, five workloads, two workers, 192 tasks, seven methods, 105 paired timed runs. Method and group order were shuffled. Selection criterion: lowest geometric mean of the five workload-level median paired runtime ratios versus fixed chunk 4. The result was `balanced_fifo_16` at approximately **0.952**. All development checksums matched. Development files are in `results_balanced_dev`.

The selected method uses each task's known work estimate to form approximately equal-cost batches, retains task order, and dispatches all batches once to a Linux process pool. No training or feedback barrier is used. `balanced_8`, `balanced_16`, `balanced_32` and fixed/standard-library baselines remain in the evaluation as comparators, but **`balanced_fifo_16` is the declared primary candidate**.

Fresh evaluation plan, fixed before seeing those results: five new seeds **5001–5005**, the same five workloads and seven methods, paired wall-clock runs including process startup and teardown. Compare the selected method with fixed chunk 4 using the five workload-level paired ratios and the combined geometric mean. Keep the raw results even if the selected method fails to beat the baseline.
