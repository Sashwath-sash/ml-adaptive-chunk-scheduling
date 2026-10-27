# Cache admission research audit — 27 October 2026

## What was changed

The native C cache now accepts `second_touch_arc` and `second_touch_s3fifo` as cheap, non-ML admission controls. Both use the same cache parent, capacity, trace, backing file, and returned-data checksum as the learned versions. A first request is served but not retained; a later miss may be admitted. The command line also accepts an optional cache capacity and model threshold, without retraining or changing the exported model. The original 512-entry result remains reproducible.

New scripts: `evaluate_admission_controls.py`, `select_admission_thresholds.py`, `evaluate_selected_thresholds.py`, and `plot_admission_capacity_study.py`. Their raw JSON outputs are saved next to the source. `capacity_read_reduction.png` plots the complete capacity sweep, including negative results.

## Experimental question and outcome

**Question:** Does the trained admission filter reduce program-issued 4-KiB backing-read calls beyond the unfiltered parent and a cheap admission rule, and does that advantage survive a change in cache budget?

At **512 entries**, the fixed 0.2 model produced fewer direct-read calls than ARC, second-touch ARC, local S3-FIFO, and second-touch S3-FIFO on all four saved streams. The ML-versus-parent reductions ranged from about 1.0% to 7.5%; no timing guarantee follows from this count metric.

At **256 entries**, the fixed model beat its parent in only 3 of 8 policy/stream comparisons. At **1,024 entries**, it beat its parent in 4 of 8. Thus a blanket claim of capacity-independent read savings is false for this implementation. Each cache entry stores a 4-KiB surrogate block, so these data budgets are 1, 2, and 4 MiB; metadata and model memory are additional.

The follow-up validation-only cutoff rule chose one threshold per cache size and parent. Its test counts beat the parent in 18 of 24 comparisons, tied in 5, and lost in 1. This is **exploratory, post hoc evidence**: the follow-up was designed after the initial capacity failures were inspected, and the held-out streams have been reused. It must not be described as a fresh blind result. The one loss is BrowseTrace A at 256 entries: calibrated ML+S3-FIFO made 10,509 reads versus the parent's 10,054, **4.53% more**.

| Data budget | Frozen 0.2: wins / 8 | Validation-selected: wins / ties / losses |
| --- | ---: | ---: |
| 256 entries (1 MiB) | 3 | 4 / 3 / 1 |
| 512 entries (2 MiB) | 8 | 8 / 0 / 0 |
| 1,024 entries (4 MiB) | 4 | 6 / 2 / 0 |

The precise parent, fixed-model, and calibrated read counts for all 24 cases are in `results_selected_thresholds_2026-10-27.json`; the capacity sweeps and full validation rankings are in the other JSON files. Every native comparison returned the same per-stream checksum. The capacity sweeps used **one run per policy** and are not a statistically supported latency experiment; their `wall_seconds` fields must not be used for a speed claim. The earlier five-run 512-entry timing measurements remain separate.

## How cutoff selection works

The scikit-learn model is frozen. For each capacity (256, 512, 1,024) and parent (ARC, local S3-FIFO), the selection script replays only the three **validation** slices: BrowseTrace A, BrowseTrace B, and NASA July. It tries cutoffs 0.05, 0.1, 0.15, 0.2, 0.3, 0.4, and 0.5. It minimizes the worst ratio of ML reads to parent reads across the three validation slices, breaking ties by mean ratio. Selected cutoffs were:

| Capacity | ARC cutoff | S3-FIFO cutoff |
| --- | ---: | ---: |
| 256 | 0.05 | 0.3 |
| 512 | 0.3 | 0.2 |
| 1,024 | 0.1 | 0.1 |

The test streams are not accessed by this script. Nonetheless, because the *idea and capacity choices* arose after looking at test failures, these new test results are exploratory, not an independent confirmatory study.

## Additional key-only transfer stress test

I also tested the frozen 512-entry model on the first 100,000 keys in the publicly hosted [`metaCDN.sample10.txt.zst` file](https://ftp.pdl.cmu.edu/pub/datasets/twemcacheWorkload/txt/). This is a **sampled, anonymized key-only stream**, not the 2025 Meta CDN dataset and not a like-for-like web request trace. It has no object sizes or URL components. For the native input, size was set to zero, the one synthetic host was shared by all keys, and URL-specific flags were zero. The exact acquired compressed bytes are pinned by SHA-256 `f5818401662c558240645a015dfbf47515c0d00feb0af6dfe7afd7938de7f3b2`. The host presented an expired TLS certificate during acquisition, so this hash supports rerun consistency but is not independent proof of source authenticity. The source file itself is not redistributed in this project.

| Policy | Direct-read calls | Change from its unfiltered parent |
| --- | ---: | ---: |
| ARC | 62,532 | — |
| Second-touch ARC | 69,067 | +10.45% |
| ML+ARC | 69,720 | **+11.49%** |
| Local S3-FIFO | 61,628 | — |
| Second-touch S3-FIFO | 68,806 | +11.65% |
| ML+S3-FIFO | 69,646 | **+13.01%** |

An independent Python ARC/S3-FIFO replay reproduced all four parent/ML counts. The classifier's ROC AUC is **0.803**, average precision **0.773**, and future-1,024-request reuse prevalence **0.370**; 41.6% of requests exceeded the 0.2 admission cutoff. Despite that ranking ability, the learned policy made *more* cache reads. This directly demonstrates that reuse classification quality is not enough to establish system benefit, especially under missing features and workload shift. These diagnostics and counts are in `results_metacdn_sample10_diagnostics.json` and `results_metacdn_sample10_100k_512.json`. The source conversion is reproducible with `prepare_metacdn_stress.py`; `evaluate_metacdn_diagnostics.py` checks model scores and independent replay counts.

## Interpretation and publication status

This is a stronger **research prototype and audit**, but it is **not yet a defensible conference submission**. Learned admission and learned cache management are established topics. The current contribution is a local integration plus a useful robustness finding, not a demonstrated new general algorithm. The 0.2 cutoff was optimized for a 512-entry experiment, and the losses at other budgets show the current learned target is not budget-aware. The calibrated cutoffs partly correct that weakness but still fail one case and have no fresh holdout.

Material evidence gaps remain: (1) new, untouched production traces with a preregistered method; (2) stronger published baseline implementations under equivalent memory and request semantics; (3) real variable-size objects and byte miss ratio; (4) separated model/metadata memory and CPU overhead, and multi-host timing; (5) a genuinely distinct capacity-aware admission algorithm with ablations; (6) a full related-work comparison and a venue-specific paper. The key-only transfer failure additionally calls for a feature design that tolerates missing URL fields, with a fresh evaluation after that design is frozen. The current S3-FIFO is a local implementation and should not be described as the authors' optimized system. The original web bodies were unavailable; each miss reads a deterministic surrogate block. A direct-read call is not a measured physical device I/O or network retrieval.

Recent work against which a novelty claim must be checked includes [S3-FIFO (SOSP 2023)](https://www.cs.cmu.edu/~rvinayak/papers/s3-fifo-sosp-2023-fifo-queues-are-all-you-need-for-cache-eviction.pdf), [GL-Cache (FAST 2023)](https://www.usenix.org/conference/fast23/presentation/yang-juncheng), [3L-Cache (FAST 2025)](https://www.usenix.org/conference/fast25/presentation/zhou-wenbin), and [Learning-Augmented Heuristics (OSDI 2026)](https://www.usenix.org/conference/osdi26/presentation/xia). The [cacheMon production trace collection](https://github.com/cacheMon/cache_dataset) includes a 2025 Meta CDN workload that is a better target for a fresh transfer test than relying only on the current historical web logs.

## Reproduce the extension

From this project folder on Windows with WSL and the existing `.venv`:

```powershell
wsl.exe -e bash -lc 'cd /mnt/c/Users/SASHWATH/Documents/Codex/2026-10-06/referenced-chatgpt-conversation-this-is-an-2/work/ml-chunk-scheduling-fresh && cc -O2 -std=c11 -Wall -Wextra -Werror cache_native.c -lm -o cache_native'
.\.venv\Scripts\python.exe evaluate_admission_controls.py --output another_512.json --capacity 512 --repeats 1
.\.venv\Scripts\python.exe evaluate_admission_controls.py --output another_256.json --capacity 256 --repeats 1
.\.venv\Scripts\python.exe evaluate_admission_controls.py --output another_1024.json --capacity 1024 --repeats 1
.\.venv\Scripts\python.exe select_admission_thresholds.py --output another_selection.json
```

The saved `evaluate_selected_thresholds.py` run expects the named sweep files from this dated extension, so it is directly reproducible inside the packaged project. The `--sync` native mode starts measurement after backing-file preparation, and its `wall_seconds` is the C request loop alone.

To repeat the separate MetaCDN key-only stress test, download the `metaCDN.sample10.txt.zst` file from the URL above into `data/`, install `requirements_research_extension.txt`, and run `python prepare_metacdn_stress.py --output cache_native_input_metacdn_sample10_100k`. The script rejects a SHA-256 mismatch. Then run `python evaluate_admission_controls.py --input-folder cache_native_input_metacdn_sample10_100k --stream-name MetaCDN-sampled --capacity 512 --repeats 1 --output another_metacdn_native.json`. The saved `evaluate_metacdn_diagnostics.py` run checks the dated native result and independent Python replay.
