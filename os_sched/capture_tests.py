"""Run the Linux test suite and save its unmodified terminal output."""
import argparse
import subprocess
import sys
from pathlib import Path


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", type=Path, default=Path("results_complete/tests.txt"))
    args = ap.parse_args()
    result = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
                            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(result.stdout, encoding="utf-8")
    print(result.stdout, end="")
    if result.returncode:
        raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
