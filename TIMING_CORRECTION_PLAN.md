# Corrected timing-boundary rerun (recorded before new measurements)

Audit found that `run_balanced` previously built its batches just before starting its timer. The planning step is small but must be included for a fair end-to-end comparison. The timer now starts **before** estimated-cost calculation, batch construction, sorting, process creation, dispatch and teardown. The selected primary method remains `balanced_32`; no method or workload parameters are changed to chase the result.

The old `results_balanced_dev`, `results_balanced_test` and `results_straggler_test` are retained as superseded records. Do not cite them as final timing evidence.

Final corrected test uses fresh, previously unseen seeds:

- Broader five-workload comparison: seeds **6001–6005**, five classes, seven methods, 175 paired runs.
- Targeted tail-straggler comparison: seeds **10001–10010**, one 40× task among the last eight of 192 tasks, seven methods, 70 paired runs.

Primary claim to test: `balanced_32` has lower paired end-to-end time than fixed chunk 4 on the targeted tail-straggler case. Report all ten ratios and the five-workload generalization check, whether positive or negative. Preserve code, input dataset, checksums and raw CSV results.
