#!/usr/bin/env python
"""Build-order gate: verify the SHARED extractor on logged samples.

Checks plumbing, not scores:
  - every sample produced a non-null extracted_answer
  - re-running extract_answer on the logged final_string round-trips
  - gold_answer parsed for every sample
  - reports shared-extractor accuracy (informational; n=15 is a plumbing test)

Usage:
  .venv/bin/python verify_extraction.py [--run-id RUN] [--arm ARM] [--dataset DS]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
from harness.extract import extract_answer  # noqa: E402


def latest_run():
    runs = sorted(glob.glob(os.path.join(ROOT, "logs", "*", "samples.jsonl")),
                  key=os.path.getmtime)
    if not runs:
        sys.exit("no logs/*/samples.jsonl found — run run_eval.py first")
    return os.path.dirname(runs[-1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--arm", default=None)
    ap.add_argument("--dataset", default=None)
    args = ap.parse_args()

    run_dir = (os.path.join(ROOT, "logs", args.run_id) if args.run_id
               else latest_run())
    path = os.path.join(run_dir, "samples.jsonl")
    rows = [json.loads(l) for l in open(path)]
    if args.arm:
        rows = [r for r in rows if r.get("arm") == args.arm]
    if args.dataset:
        rows = [r for r in rows if r.get("dataset") == args.dataset]
    if not rows:
        sys.exit(f"no matching samples in {path}")

    print(f"run_dir: {run_dir}")
    print(f"samples: {len(rows)}  (arm={args.arm or 'all'} dataset={args.dataset or 'all'})")
    print("-" * 100)
    print(f"{'#':>2}  {'problem':<52}  {'extracted':>12}  {'gold':>10}  {'ok':>3}  rt")
    print("-" * 100)

    bad_extract, bad_roundtrip, bad_gold, correct = 0, 0, 0, 0
    for r in rows:
        idx = r.get("idx")
        prob = (r.get("problem") or "").replace("\n", " ")[:52]
        ext = r.get("extracted_answer")
        gold = r.get("gold_answer")
        fmt = r.get("fmt")
        final = r.get("final_string") or ""
        rt = extract_answer(final, fmt) if fmt else None
        rt_ok = (str(rt) == str(ext)) if ext is not None else (rt is None)
        sc = r.get("shared_correct")
        if ext is None and not r.get("error"):
            bad_extract += 1
        if not rt_ok:
            bad_roundtrip += 1
        if gold is None:
            bad_gold += 1
        if sc:
            correct += 1
        flag = "Y" if sc else ("!" if r.get("error") else "n")
        print(f"{idx:>2}  {prob:<52}  {str(ext):>12}  {str(gold):>10}  {flag:>3}  "
              f"{'ok' if rt_ok else 'RT-FAIL'}")
        if r.get("error"):
            print(f"      error: {r['error']}")

    print("-" * 100)
    n = len(rows)
    print(f"extracted non-null (no error): {n - bad_extract}/{n}")
    print(f"final_string round-trips:      {n - bad_roundtrip}/{n}")
    print(f"gold parsed:                   {n - bad_gold}/{n}")
    print(f"shared-extractor exact-match:  {correct}/{n}  "
          f"({correct / n:.0%})   [informational — plumbing test]")
    print("-" * 100)

    problems = []
    if bad_extract:
        problems.append(f"{bad_extract} samples with null extraction and no logged error")
    if bad_roundtrip:
        problems.append(f"{bad_roundtrip} samples where extract_answer(final_string) "
                        f"!= extracted_answer")
    if bad_gold:
        problems.append(f"{bad_gold} samples with unparsed gold")
    if problems:
        print("EXTRACTION PLUMBING ISSUES:")
        for p in problems:
            print("  - " + p)
        sys.exit(1)
    print("extraction plumbing OK")


if __name__ == "__main__":
    main()
