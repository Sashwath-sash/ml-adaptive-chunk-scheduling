"""Make an out-of-domain stress trace from a sampled Meta CDN key-only dataset.

This source lacks object sizes and URL structure. The conversion supplies zero
size and no host/static/query metadata, so it is not equivalent to the web
traces used to train the model or a variable-size CDN cache evaluation.
"""
import argparse
import hashlib
import json
from pathlib import Path

import zstandard


ROOT = Path(__file__).resolve().parent
SOURCE_URL = "https://ftp.pdl.cmu.edu/pub/datasets/twemcacheWorkload/txt/metaCDN.sample10.txt.zst"
EXPECTED_SHA256 = "f5818401662c558240645a015dfbf47515c0d00feb0af6dfe7afd7938de7f3b2"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "data/metaCDN.sample10.txt.zst")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--requests", type=int, default=100000)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists")
    if args.requests < 1:
        parser.error("requests must be positive")
    digest = hashlib.sha256(args.source.read_bytes()).hexdigest()
    if digest != EXPECTED_SHA256:
        parser.error(f"source SHA-256 mismatch: {digest}")
    keys = {}
    lines = []
    with args.source.open("rb") as raw:
        with zstandard.ZstdDecompressor().stream_reader(raw) as stream:
            import io
            reader = io.TextIOWrapper(stream, encoding="utf-8")
            for raw_key in reader:
                key = raw_key.strip()
                if not key or not key.isdecimal():
                    raise ValueError(f"unexpected source key: {key!r}")
                if key not in keys:
                    keys[key] = len(keys)
                length = len(key)
                lines.append(f"{keys[key]} 0 0 {length} 0 0 {length}")
                if len(lines) == args.requests:
                    break
    if len(lines) != args.requests:
        raise ValueError(f"source ended after {len(lines)} requests")
    args.output.mkdir(parents=True)
    (args.output / "test_trace.txt").write_text(
        f"{len(lines)} {len(keys)} 1\n" + "\n".join(lines) + "\n")
    (args.output / "model.txt").write_bytes(
        (ROOT / "cache_native_input_three_source_scripted/model.txt").read_bytes())
    info = {
        "source_url": SOURCE_URL,
        "compressed_sha256": digest,
        "rows": len(lines), "unique_keys": len(keys),
        "source_sampling": "sample10: source naming suggests one of ten requests; do not infer unsampled rates",
        "conversion": "Anonymized numeric ID becomes key; size=0, host=0, path and key lengths=ID length, static/query=0",
        "limitation": "Out-of-domain key-only stress test; no object bytes, sizes, real URL features, or 2025 Meta trace",
        "tls_note": "Source host served an expired TLS certificate on download; file hash pins the acquired bytes, not source authenticity",
    }
    (args.output / "manifest.json").write_text(json.dumps(info, indent=2) + "\n")
    print(json.dumps(info, indent=2))


if __name__ == "__main__":
    main()
