# Final cache project: offline viva guide

**Student:** Sashwath J, 24BAI0059  
**Final title:** Machine Learning Assisted Adaptive Chunk Caching for I/O Workloads  
**Read this on a phone:** This file has the explanation, results, code map, commands, and likely questions. The [presentation](final-cache/Review2_Review3_Combined_Project_Presentation.pptx) and [illustrated technical report](final-cache/Review3_Project_Technical_Report.pdf) are also here. The [complete evidence ZIP](final-cache/hybrid_cache_review_evidence_v12.zip) contains code, data, saved model, results and plots. A [later research extension](final-cache/research-extension-2026-10-27/RESEARCH_STATUS.md) tests cheap admission controls, different cache sizes, and a sampled key-only transfer stream; it finds important failures beyond the 512-entry setting used below.

## The 60-second explanation

> My final project tests learned admission in a small I/O chunk cache. The cache holds 512 blocks of 4 KiB, or 2 MiB of data. On a miss, the native C program fetches and serves the block. It then uses a frozen trained model to decide whether to retain that block. Low-scoring blocks bypass insertion; high-scoring blocks enter ARC or a local S3-FIFO replacement policy. On four request streams, the ML-assisted versions made fewer backing-file direct-read calls than their own parent policies, with reductions of about 1% to 7.5%. Every policy returned the same checksum. Runtime was mixed, so the supported result is better read-call efficiency in this prototype, not a universal speedup.

## 1. Why the problem matters

A **cache hit** means the requested block is already in the 512-slot cache and needs no backing-file read. A **miss** means it is absent, so the program reads the 4 KiB backing block and returns it. After a miss, the cache must decide whether to retain that block. Retaining a block that is not used again may evict one that would have been useful, creating future misses. The learned decision tries to reduce this cache pollution. A bypassed block is still served correctly; only its retention changes.

## 2. What is learned

An offline request gets label 1 when its key reappears within the next **1,024 requests**, otherwise 0. This future window is used only to create training/evaluation labels. The online model sees eight features from the current request and past history:

| Feature | Meaning |
| --- | --- |
| Response size | Recorded object size |
| Previous key frequency | Earlier requests for the same key |
| Recency | Requests since the previous appearance of that key |
| Previous host frequency | Earlier requests from the same host |
| Path length | Length of the lowercased URL path |
| Static suffix | Flag for CSS, JS, common image or font extensions |
| Query flag | Whether the URL contains a query string |
| Key length | Length of the full cache key |

Training uses scikit-learn's `HistGradientBoostingClassifier`, with up to 100 boosting stages, 15 leaves per tree, at least 40 samples per leaf, learning rate 0.07 and L2 regularization 2. Validation compared six combinations: 40 or 100 stages, each with thresholds 0.2, 0.4 or 0.6. The selected export uses **100 stages, 2,900 stored nodes and threshold 0.2**. Its selection objective used earlier validation streams, not the final ARC/S3-FIFO hybrid results. The chosen threshold favors admitting potentially reusable blocks: a score below 0.2 bypasses insertion; a score at least 0.2 passes the block to a parent cache policy.

## 3. How Python training becomes C inference

`train_three_source_cache.py` fits the model and exports every tree's numeric nodes: feature index, split threshold, left/right child, missing-value route and leaf value. `export_cache_native.py` writes this model and a numeric request trace for native replay. At startup, `cache_native.c` loads the node arrays from `model.txt`. On a miss it builds `double x[8]`, traverses the exported trees in `predict_early`, adds their reached leaf values and returns a binary admit/bypass decision. It can stop early when the remaining trees cannot change which side of the threshold the final score will take. **There is no Python or scikit-learn inference inside the measured C request loop.**

## 4. How Linux is involved

The cache experiment is a **user-space native C program executed under Linux through WSL**. It uses an aligned 4 KiB `O_DIRECT` `pread` call on cache misses. ARC and the local S3-FIFO implementation manage admitted cache blocks. This is related to OS storage/cache management, but it **does not patch the Linux kernel**, replace its scheduler or demonstrate a production shared cache. A direct-read call is a program-level measured I/O request; it does not prove a physical disk transaction.

## 5. Data and split design

The input is an ordered request trace. Order matters because earlier requests determine cache contents and online history. BrowseTrace A has 49,473 training, 16,491 validation and 16,491 later-test requests. BrowseTrace B has 214,669 training, 71,556 validation and 71,557 later-test requests. NASA **July web-server** requests contribute 150,000 training and 50,000 validation requests. Its later tail was excluded after an earlier transfer failure. NASA **August web-server** requests supply a later-time final test of 100,000 requests. The Calgary web-server log supplies a separate-server final test of 100,000 requests. NASA here means historical website traffic, not spacecraft data.

The original response bodies are unavailable. The C program uses deterministic surrogate 4 KiB backing blocks and verifies returned data by checksum. The request keys/order come from the traces. BrowseTrace is a separate trace source; do not describe all four streams as one uniform real production workload. Calgary was inspected before the later ML+S3-FIFO pairing, so that particular pairing is **not fully blind**.

## 6. Actual request workflow

1. Look for the requested key in the 512-entry cache.
2. Hit: return the cached block.
3. Miss: issue the aligned 4 KiB backing-file read and serve that data.
4. On ML policies, compute eight current/past features and evaluate the exported trees in C.
5. Score below 0.2: bypass insertion. Score at least 0.2: insert through ARC or local S3-FIFO.
6. Update history and the output checksum. Repeat for the next request.

The ML model is an **admission filter**. ARC/S3-FIFO are **replacement policies** that manage which admitted blocks remain in the bounded cache. The fair comparisons are ARC versus ML+ARC and local S3-FIFO versus ML+S3-FIFO on the same stream and capacity.

## 7. Measured results and what each number means

Direct-read calls count cache misses that requested a backing-file read. Fewer means greater read-call efficiency in this replay. Hit rate is hits divided by all requests. Loop time is the C request-loop elapsed time and includes inference. Equal checksums show equal returned data.

| Final stream | Requests | ARC reads | ML+ARC | Local S3-FIFO reads | ML+S3-FIFO |
| --- | ---: | ---: | ---: | ---: | ---: |
| BrowseTrace A | 16,491 | 7,430 | 7,104 | 7,773 | 7,336 |
| BrowseTrace B | 71,557 | 17,913 | 17,740 | 18,950 | 18,586 |
| NASA August | 100,000 | 8,792 | 8,130 | 8,349 | 8,048 |
| Calgary | 100,000 | 16,493 | 15,718 | 15,406 | 15,177 |

The eight within-parent read reductions range from about **1.0% to 7.5%**. Example: NASA August ML+ARC saves `8792 - 8130 = 662` calls, or `662/8792 = 7.5%`. Checksums match across policies for each stream. Independent Python reference replays match native miss counts.

Saved five-run median loop time improved in six of eight parent-versus-hybrid comparisons. ML+ARC was slower than ARC on BrowseTrace B (about 2.894 s vs 2.866 s); ML+S3-FIFO was slower than its parent on NASA August (about 1.375 s vs 1.322 s). A fresh single Calgary run reproduced the exact read counts and checksums but its elapsed times differed from the saved medians. The defensible claim is **fewer requested backing reads on these tested streams**, not guaranteed lower runtime.

Held-out classifier ROC AUC ranged from about 0.816 to 0.962. ROC AUC tests score ranking; precision/recall at 0.2 test classification of the defined future-reuse label. These model metrics do not by themselves establish cache savings. The native read-count comparison is the system-level test.

## 8. What to run and show in the lab

From PowerShell on the Windows/WSL machine:

```powershell
cd "C:\Users\SASHWATH\Documents\Codex\2026-10-06\referenced-chatgpt-conversation-this-is-an-2\work\ml-chunk-scheduling-fresh"
python demo_hybrid_final.py
python demo_hybrid_final.py --live calgary
```

The first command checks saved source/model/count/checksum evidence and prints the four-stream comparison. The second compiles the native C program with GCC under WSL and runs a fresh Calgary replay. Allow roughly a minute or two. The **read counts and checksums** should match; `loop=` timings can change. Internet access is not needed when the local source, data, Python and WSL/GCC are already installed. The ZIP is an evidence package, not a one-click installer; set up those tools before the review.

Show `cache_native.c` around lines 209–263: hit/miss, `pread`, `double x[8]`, `predict_early`, admission and checksum. Show lines 18–34 for the exported-tree traversal. Show `train_three_source_cache.py` for the scikit-learn fit and validation selection. Show `results_cache_three_source_v1/model.joblib` and `hgb.json` as the saved fitted model and export, not as handwritten C rules. Do not rerun training or the long benchmark during a short viva. Some scripts intentionally refuse to overwrite saved outputs.

## 9. Review 2 continuity

Review 2 studied ML decisions for **CPU work-chunk scheduling**. Its available-machine tests did not establish a reliable overall completion-time gain. The final project changed the managed resource to **I/O cache chunks** while retaining the broader question of whether a learned chunk-management decision helps an OS-related workload. The old scheduling code/results are preserved in this repository as historical Review 2 work, but they are **not** the final cache implementation and their numbers are not combined with cache results. Tell the reviewer this openly; approval of the changed scope has not been assumed.

## 10. Novelty answer and hard follow-ups

**“Is ML cache admission new?”** No. CACHEUS, Baleen and other systems establish learned caching prior art. The project contribution is this specific frozen reuse-filter integration in native C before two parent policies, the fair within-parent tests, independent count and checksum checks, and disclosure of workloads/timings where benefits are limited. Do not claim a new universal algorithm or a world-first invention. If the assessment demands original algorithmic novelty, the current evidence does not establish it.

**“Why does bypass still read the block?”** The request still needs its data. Bypass means the fetched block will not occupy cache space. That can avoid a later read by keeping a more useful block resident.

**“Does the model see the future?”** Future occurrences create offline labels. Runtime features are current/past only. One replay-only convention uses the known trace length as the recency sentinel for unseen keys; replace it with a fixed sentinel in production. It does not look up the key's future occurrence.

**“Why might reads improve but time worsen?”** ML evaluation consumes CPU time, and single-host loop timing varies. The tests do not isolate every cause. Read-call count and elapsed time are distinct metrics.

**“Does O_DIRECT prove fewer physical disk operations?”** No. It demonstrates fewer direct-read *calls requested by this program* on misses. Physical-device operations, energy and network latency were not measured.

**“Is this a Linux kernel scheduler or production cache?”** No. It is a native C user-space cache replay on Linux/WSL. It has no measured multiprocess shared-cache throughput result.

**“Why compare with both ARC and S3-FIFO?”** Each is a parent replacement policy. Comparing each parent with the same parent plus ML isolates the admission filter better than comparing different policies against one another.

**“How do you know the output is still correct?”** Every policy returns the same per-stream checksum, backing data carries deterministic markers, and independent Python replays match native miss counts.

**“What is incomplete?”** The working prototype, data, plots and demo exist. The supplied Review 3 **final paper** guideline also requires an original analytical survey of at least 30 relevant 2021–2026 papers with APA references and matching in-text citations. The technical report and presentation have three verified prior-work anchors, so they do **not** yet satisfy that paper requirement.

## 11. Files worth opening from a phone

- [Latest combined PPT](final-cache/Review2_Review3_Combined_Project_Presentation.pptx)
- [Illustrated technical report PDF](final-cache/Review3_Project_Technical_Report.pdf)
- [Native C cache and ML inference](final-cache/cache_native.c)
- [Training code](final-cache/train_three_source_cache.py)
- [Feature/label code](final-cache/cache_admission_probe.py)
- [Model export code](final-cache/export_cache_native.py)
- [Live demo script](final-cache/demo_hybrid_final.py)
- [Frozen model and detailed result record](final-cache/MODEL_AND_RESULTS_RECORD.md)
- [Complete source/data/results archive](final-cache/hybrid_cache_review_evidence_v10.zip)

### Prior-work anchors

Rodriguez et al. (2021), *Learning cache replacement with CACHEUS*, USENIX FAST. Yang et al. (2023), *FIFO queues are all you need for cache eviction*, ACM SOSP. Wong et al. (2024), *Baleen: ML admission and prefetching for flash caches*, USENIX FAST. These are context sources, **not** a completed 30-paper survey.
