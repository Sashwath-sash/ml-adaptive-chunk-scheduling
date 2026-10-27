# Frozen ML admission model and measured results

See [ARCHITECTURE.md](./ARCHITECTURE.md) for the complete model-training,
native request-path, and verification diagram.

This record describes the model actually used by the native cache experiment. It is an evidence file for review preparation, not a claim of a new general cache algorithm or a student-authored research paper.

## Decision being learned

For each requested cache key, the supervised target is 1 if the same key appears within the next 1,024 requests in its training slice; otherwise it is 0. This is a *future reuse* label, available for training but not to the live system. On a cache miss, the C program evaluates the frozen model. It serves the requested 4 KiB backing block either way. A score below 0.2 bypasses cache insertion; a score at or above 0.2 passes the block to ARC or the local S3-FIFO policy. The cache holds 512 blocks (2 MiB).

The end of a finite trace is right-censored: a key may be labeled 0 because later requests were not observed. The evaluation script uses the same 1,024-request labeling rule, so classifier diagnostics should be interpreted with this limitation. Classification quality is not itself evidence of fewer device transactions or lower latency; the native cache replay supplies that separate test.

## Training configuration

`train_three_source_cache.py` fits `sklearn.ensemble.HistGradientBoostingClassifier` with `max_iter=100`, `max_leaf_nodes=15`, `min_samples_leaf=40`, `learning_rate=0.07`, `l2_regularization=2`, and `random_state=811`. The exported online model contains 100 boosting stages and 2,900 tree nodes in total. The threshold 0.2 and stage count 100 were selected among 6 candidate combinations (40 or 100 stages; threshold 0.2, 0.4 or 0.6) using only the three validation streams. The selection objective minimized the worst ratio of ML-policy misses to the best tested simple validation policy, breaking ties by mean ratio and then number of stages. It was **not** selected to optimize the later ARC and S3-FIFO hybrid results.

| Source | Training requests | Validation requests | Final test |
|---|---:|---:|---|
| BrowseTrace A | 49,473 | 16,491 | last 16,491 requests |
| BrowseTrace B | 214,669 | 71,556 | last 71,557 requests |
| NASA July | 150,000 | 50,000 | July tail excluded after previous transfer failure |
| NASA August | 0 | 0 | last 100,000 valid GET responses |
| Calgary | 0 | 0 | last 100,000 valid GET responses from another server |

The BrowseTrace partitions are chronological 60/20/20; integer rounding explains the one-request difference between B validation and test. Training totals 414,142 requests and validation totals 138,047 requests. The NASA July source is a 300,000-request extracted slice; its last 100,000 were excluded after an earlier model failed there. August is a later-time test. Calgary is a new-server test of the ML+ARC rule, but the ML+S3 rule was explored after inspecting Calgary plain-policy results and is not blind on that stream.

## Eight online features

All are computed from the current request and previous requests only. URL-derived features use the anonymized cache key as available in the source trace.

| Index | Feature | Exact form | Reason to test |
|---:|---|---|---|
| 1 | Response size | `log1p(max(0, object_size_bytes))` | Object size may differ by resource type |
| 2 | Previous key frequency | `log1p(number of earlier requests for this key)` | Repeated keys are candidates for reuse |
| 3 | Recency | `log1p(request index - previous index)`; unseen keys use `len(slice)+1` | Recent reuse may continue |
| 4 | Previous host frequency | `log1p(number of earlier requests for host)` | Host activity may reflect locality |
| 5 | Path length | Number of characters in lowercased URL path | Resource-structure proxy |
| 6 | Static suffix | 1 for CSS, JS, PNG, JPG, JPEG, SVG, WOFF or WOFF2 | Static resources can be revisited |
| 7 | Query flag | 1 when URL contains a query string | Query URLs may have different reuse |
| 8 | Key length | Number of characters in full cache key | Resource-structure proxy |

The unseen-key recency uses the known slice length as a constant. This does not inspect a future occurrence of that key, but it is a trace-replay convention and should be replaced by a fixed runtime sentinel in a production design. Feature association is predictive, not proof of causation.

## Independent held-out classifier diagnostics

`evaluate_frozen_model.py` loads the saved `.joblib` file and computes these values without retraining. AUC measures ranking of positive versus negative examples (0.5 is random ranking). Precision is the fraction of score-at-least-0.2 decisions that truly reused within the 1,024-request horizon. Recall is the fraction of those reuse events retained by that threshold. High recall is expected because 0.2 is a permissive admission threshold.

| Test stream | Requests | Positive share | ROC AUC | Average precision | Precision at 0.2 | Recall at 0.2 | Brier score |
|---|---:|---:|---:|---:|---:|---:|---:|
| BrowseTrace A | 16,491 | 0.576 | 0.862 | 0.853 | 0.720 | 0.993 | 0.143 |
| BrowseTrace B | 71,557 | 0.722 | 0.816 | 0.920 | 0.744 | 0.997 | 0.150 |
| NASA August | 100,000 | 0.836 | 0.962 | 0.993 | 0.885 | 0.991 | 0.058 |
| Calgary | 100,000 | 0.761 | 0.889 | 0.965 | 0.805 | 0.982 | 0.118 |

The full confusion counts, log loss and unrounded values are in `final_review_materials/output/frozen_model_diagnostics.json`. The black-and-white ROC and calibration figure is `final_review_materials/output/frozen_model_diagnostics_bw.png`, generated by `plot_frozen_model_diagnostics.py`. The curves show that score ranking transfers differently across sources; the classifier is not perfectly calibrated on every source.

## Native system outcomes

The independent native replay (`cache_native.c`) performs aligned `O_DIRECT` read calls on misses. Counts exactly match separate Python reference replays, and output checksums are identical among compared policies for each stream. Five-run alternating-order median loop timing is recorded separately. The live run can vary substantially: a fresh Calgary replay on this host returned the exact saved read counts but had different elapsed times, including an unusually slow ARC run. Treat saved timing as single-host observations, not stable speedup guarantees.

| Stream | ARC reads | ML+ARC reads | ARC read reduction | S3 reads | ML+S3 reads | S3 read reduction |
|---|---:|---:|---:|---:|---:|---:|
| BrowseTrace A | 7,430 | 7,104 | 4.4% | 7,773 | 7,336 | 5.6% |
| BrowseTrace B | 17,913 | 17,740 | 1.0% | 18,950 | 18,586 | 1.9% |
| NASA August | 8,792 | 8,130 | 7.5% | 8,349 | 8,048 | 3.6% |
| Calgary | 16,493 | 15,718 | 4.7% | 15,406 | 15,177 | 1.5% |

Median loop time improved in six of eight parent-versus-hybrid comparisons. ML+ARC was slower than ARC on BrowseTrace B (2.894 versus 2.866 seconds), and ML+S3 was slower than S3 on NASA August (1.375 versus 1.322 seconds). Model evaluation adds CPU work, but the experiment does not isolate every timing component well enough to assign a proven cause to each difference. The figure `hybrid_cache_evidence_bw.png` shows both read and time differences with the negative cases.

## Reproduction and boundaries

Run `python demo_hybrid_final.py` from the project directory to verify saved evidence. `python demo_hybrid_final.py --live calgary` compiles and runs a fresh Linux direct-I/O replay through WSL/GCC. `evaluate_frozen_model.py` and `plot_frozen_model_diagnostics.py` reproduce the new model diagnostics with the project's `.venv` dependencies. The `.joblib` model should be loaded only from this trusted project path because pickle-family formats can execute code on load.

This is a user-space prototype, not an in-kernel cache. The cache uses deterministic surrogate backing blocks because the original web response bodies are unavailable. Fewer direct-read calls mean fewer requested backing-file reads in this implementation; they do not prove fewer physical device transactions or lower real-world network latency. The local S3-FIFO implementation does not establish parity with the official optimized version. ML cache admission and the parent replacement algorithms have prior art; the supported contribution is this integration, its measured tests, and its disclosed failure cases.
