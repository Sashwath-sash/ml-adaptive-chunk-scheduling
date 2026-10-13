# Tail-straggler test plan recorded before measurement

Question: can estimated-cost batching with longest batches first (`balanced_32`) beat fixed chunk 4 when one expensive CPU task is near the end of a queue?

Workload: 192 deterministic compiled-C CPU tasks, two Linux worker processes, one task with 40× the nominal work randomly placed among the final eight task slots. Other task costs vary by ±10%. The exact task inputs and spike index will be saved. This is a deliberately targeted stress case, **not** a general-purpose workload or a production trace.

Fresh paired evaluation: seeds **8001–8010**, ten repeats, seven methods (fixed 4, fixed 16, Python `Pool.map` chunk 16, balanced 8/16/32 and balanced FIFO 16). Method and repeat order will be shuffled; every method must return the same checksum. The primary comparison is `balanced_32` versus paired fixed 4, using median end-to-end wall-clock time and median paired runtime ratio. Timing includes worker startup, dispatch and teardown. If the ratio is not below 1, report failure honestly.

The five-workload experiment on seeds 5001–5005 remains the broader generalization check; a win in this stress case must not be presented as a win everywhere.
