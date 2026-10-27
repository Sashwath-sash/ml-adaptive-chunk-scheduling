# Review 2 to final project transition

## Project title

**Review 2:** Machine-Learning-Assisted Adaptive Chunk Scheduling for Multiprocessing Workloads

**Final scope:** Machine-Learning-Assisted Adaptive I/O Chunk Caching for Multiprocessing Workloads

This is a scope change chosen by the student, not a claim that the reviewer has already approved it. It keeps ML-guided decisions over chunks under concurrent workloads, but the resource being managed changes from CPU work assignment to bounded I/O cache space. The Review 2 report and final implementation must not be described as the same program.

## Why the direction changed

The Review 2 prototype compared decision-tree and cost-based CPU chunk schedulers. Its measurements did not show a reliable improvement in overall completion time on the available machine. Improving one intermediate quantity, such as balance, was not enough to support the intended final claim. The final work therefore asks a narrower OS question with a directly measurable outcome: can a learned admission rule keep useful I/O chunks in a fixed-size cache and reduce backing-file reads while the system serves the same request stream?

The failed CPU result is a motivation, not evidence that all CPU scheduling is ineffective. The new I/O cache is an evolution of the research objective, not a continuation of the old implementation.

## What is genuinely implemented

The native C program replays real request traces through a 512-entry cache of 4-KiB blocks on Linux under WSL. A cache miss issues an aligned `O_DIRECT` read. A frozen 100-stage gradient-boosted model uses current request metadata and prior request history to estimate near-term reuse. Low-scoring missed chunks are served without being admitted; admitted chunks are managed by ARC or S3-FIFO. A separate Python implementation independently checks the cache-miss counts, and checksums confirm the same output is served by all policies.

The measurable benefit is fewer direct-read calls relative to the same parent replacement policy. On four held-out streams, adding ML admission reduced ARC's read count by 1.0%-7.5% and S3-FIFO's by 1.5%-5.6%. Wall-clock time is mixed, so the project must not be presented as universally faster. See `HYBRID_SYSTEM_EVIDENCE.md` for every count, timing, data split, and failure.

## What to say if the reviewer asks why this still fits

“Review 2 studied ML decisions for CPU work chunks. That implementation did not reliably improve total time, so I changed the managed resource to I/O chunks while keeping the question of whether a learned decision improves a chunk-management policy. The final implementation uses ML for cache admission and compares it with the same ARC and S3-FIFO policies without ML. The measured advantage is fewer direct reads, not a guaranteed speedup. I am showing the changed scope openly because it is not the same code as Review 2.”

## What not to claim

- Do not say Review 2 already contained this cache implementation.
- Do not call it an in-kernel scheduler, physical-disk I/O measurement, or network-cache speedup.
- Do not claim that ML cache admission has never been studied. Existing work includes learned admission and S3-FIFO's comparison with it.
- Do not say every workload is faster. Two policy/trace timing comparisons got worse.
- Do not present the technical evidence package as the student-authored final paper or as a completed 30-paper survey.

## Remaining submission work

The demonstration and source are available. The formal Review 3 submission still needs the student's original paper, a verified recent literature survey meeting the supplied guideline, and a clear explanation of the scope change to the reviewer. That work is separate from the running prototype; no placeholder citations or invented novelty statement should be used to fill it.
