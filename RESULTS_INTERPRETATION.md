# Results interpretation (measured, not projected)

The final Linux run used two worker processes, 192 tasks per run, five workloads, and five disjoint test seeds. All methods produced matching checksums within each workload/seed group. The main experiment contains 200 timed runs; a separate randomized-order comparison with existing Python APIs contains 275 timed runs. Six automated tests passed. See `results_final_linux/validation.json`, both raw CSV files and `tests.txt`.

The trained tree achieved 44/60 = 73.3% exact chunk-label accuracy on held-out profiling windows. The most common label alone occurred in 39/60 = 65% of those windows, so the gain over that simple label baseline is modest. Exact label accuracy does not imply faster total runtime.

## Main end-to-end result

Median wall-clock seconds across five test seeds (lower is better):

| Workload | Fixed chunk 4 | Decision tree | Guarded tree |
|---|---:|---:|---:|
| Uniform | 0.370 | 0.406 | 0.400 |
| Moderate variance | 0.385 | 0.424 | 0.401 |
| High variance | 0.390 | 0.438 | 0.450 |
| Phase shift | 0.391 | 0.422 | 0.443 |
| Prime scan | 0.198 | 0.207 | 0.213 |

The tree did **not** beat fixed chunk 4 on median in these workloads. Its median paired runtime ratio was about 1.08–1.13, depending on the workload; guarded-tree ratios were about 1.05–1.18. The guard demonstrably changes the next chunk when measured task cost rises, but this did not translate into a consistent runtime benefit. The online methods use multiple synchronized dispatch rounds; that overhead plausibly contributes to the difference, although these measurements alone do not isolate the cause. Decision latency is recorded separately in `summary.csv` and is much smaller than the whole-run difference.

## Existing-option comparison

The separate paired benchmark used the same task generation, two-worker limit and five test seeds. It compared fixed chunks, rule, tree and guarded tree against `multiprocessing.Pool.map`, `Pool.imap_unordered` and `concurrent.futures.ProcessPoolExecutor.map` at chunk sizes 4 and 16. In the uniform class, for example, median times were 0.379 s for `Pool.map(..., chunksize=4)`, 0.375 s for `Pool.map(..., chunksize=16)`, 0.365 s for `ProcessPoolExecutor.map(..., chunksize=16)`, and 0.421 s for the tree. Across the other classes, the best standard-library option varied; there was no consistent tree advantage. Full 55-row medians and all 275 individual runs are in `existing_options_summary.csv` and `existing_options_raw.csv`.

The comparison is end-to-end and practical, but the built-in APIs and custom scheduler have different internal dispatch paths. It should not be described as a controlled same-internals microbenchmark. The implementation is real and demonstrable, but its current performance hypothesis is **not supported** by these five small workloads on this one host. Larger tasks, less frequent decisions, more workers, real traces and additional machines are reasonable next experiments, not results already achieved.
