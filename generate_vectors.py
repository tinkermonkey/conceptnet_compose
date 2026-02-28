#!/usr/bin/env python3
"""
Convert Numberbatch text embeddings to the HDF5 format expected by the
official conceptnet_web API (data/vectors/mini.h5).

Reads:  data/raw/numberbatch-en-19.08.txt
Writes: data/vectors/mini.h5

Usage:
    pip install pandas tables numpy
    python generate_vectors.py
"""
import sys
import time
from pathlib import Path

INPUT  = Path("data/raw/numberbatch-en-19.08.txt")
OUTPUT = Path("data/vectors/mini.h5")


def main():
    if not INPUT.exists():
        print(f"ERROR: {INPUT} not found. Run the data-loader first.")
        sys.exit(1)

    if OUTPUT.exists():
        print(f"{OUTPUT} already exists — delete it to regenerate.")
        sys.exit(0)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    try:
        import numpy as np
        import pandas as pd
    except ImportError:
        print("ERROR: missing dependencies. Run: pip install pandas tables numpy")
        sys.exit(1)

    total_lines = sum(1 for _ in INPUT.open()) - 1  # subtract header
    print(f"Reading {total_lines:,} vectors from {INPUT} ...")

    index, rows = [], []
    start = time.time()

    with INPUT.open() as f:
        next(f)  # skip "num_words dimensions" header
        for i, line in enumerate(f, 1):
            parts = line.rstrip().split(" ")
            word = parts[0]
            if not word.startswith("/c/"):
                word = f"/c/en/{word}"
            index.append(word)
            rows.append(np.array(parts[1:], dtype="float32"))

            if i % 50_000 == 0 or i == total_lines:
                elapsed = time.time() - start
                rate = i / elapsed
                remaining = (total_lines - i) / rate if rate else 0
                print(f"  {i:>7,} / {total_lines:,}  "
                      f"({rate:,.0f} vectors/s, "
                      f"{remaining:.0f}s remaining)")

    print(f"\nBuilding DataFrame ({len(index):,} vectors × {len(rows[0])} dims) ...")
    df = pd.DataFrame(rows, index=index, dtype="float32")

    print(f"Writing {OUTPUT} ...")
    df.to_hdf(OUTPUT, key="mat", encoding="utf-8")

    size_mb = OUTPUT.stat().st_size / 1_048_576
    elapsed = time.time() - start
    print(f"\nDone in {elapsed:.0f}s — {OUTPUT} ({size_mb:.0f} MB)")


if __name__ == "__main__":
    main()
