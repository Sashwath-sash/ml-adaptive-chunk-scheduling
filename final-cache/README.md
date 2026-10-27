# Review 3 cache project

The [final report PDF](final_review_materials/output/Review3_Final_Submission_Refined_Sashwath_J.pdf) describes the completed user-space I/O chunk cache. An [editable Word copy](final_review_materials/output/Review3_Final_Submission_Refined_Sashwath_J.docx) is also included. The native implementation is `cache_native.c`; `train_three_source_cache.py` and `export_cache_native.py` produce the frozen model used by its admission path.

## Check the saved results

From this directory, run:

```text
python demo_hybrid_final.py
python verify_admission_extension.py
```

The first command checks input hashes, checksums, timing records and the four-stream read-count table. The second checks the parent, second-touch and ML comparisons, the capacity study and the key-only stress result. Both commands read saved results; neither retrains the model.

## Run the native program again

On Windows with WSL and GCC available:

```text
python demo_hybrid_final.py --live calgary
```

The script compiles `cache_native.c` in Linux and replays the Calgary test input through ARC, ML+ARC, local S3-FIFO and ML+S3-FIFO. Expected direct-read counts are 16,493; 15,718; 15,406; and 15,177. All four policies must return the same checksum. Loop times depend on the host and are not expected to match the report exactly.

The `cache_native_input_*` folders contain the fixed traces and exported model needed for this replay. The `data/` folder holds derived request data and manifests used by the saved-result checks. The `results_*.json` files and `final_review_materials/` sources support the tables and figures. The [research status note](research-extension-2026-10-27/RESEARCH_STATUS.md) records the capacity and transfer checks, including where ML increased read calls.
