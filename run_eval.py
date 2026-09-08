#!/usr/bin/env python
"""Baseline evaluation harness for LLM math reasoning.

Runs (arm x dataset) cells through lm-eval-harness, where each cell presents the
full orchestrator+solver exchange as a single generate() response. Emits:

  logs/<run_id>/samples.jsonl     per-sample: orchestrator out, tool calls,
                                  solver out, extracted answer, gold answer,
                                  native + shared-extractor score
  logs/<run_id>/llm_calls.jsonl   every LLM request/response/usage
  results/<run_id>/results_table.md   arm x dataset table + pointer to the log

Usage:
  source ./.env
  .venv/bin/python run_eval.py --arms direct --datasets gsm8k --mode single
  .venv/bin/python run_eval.py --arms direct --datasets gsm8k --mode two_model
  .venv/bin/python run_eval.py            # everything in config.yaml
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys

import yaml

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from harness.extract import extract_gold, is_correct  # noqa: E402
from harness.lm_wrapper import MathEvalsLM  # noqa: E402
from harness.models import ModelPair  # noqa: E402
from harness.pipeline import Pipeline  # noqa: E402
from harness.samplelog import SampleLogger  # noqa: E402


def load_config():
    with open(os.path.join(ROOT, "config.yaml")) as fh:
        return yaml.safe_load(fh)


def _context_of(sample):
    args = sample.get("arguments")
    if isinstance(args, dict):
        first = next(iter(args.values()))
        if isinstance(first, dict):
            return first.get("arg_0")
        if isinstance(first, (list, tuple)):
            return first[0]
    if isinstance(args, (list, tuple)) and args:
        return args[0][0]
    return None


def _native_score(sample):
    return {k: v for k, v in sample.items()
            if k in ("exact_match", "acc", "acc_norm") or k.endswith("_stderr")}


def run_cell(arm, ds_name, ds_cfg, cfg, mode, limit, logger, task_manager):
    from lm_eval import simple_evaluate

    fmt = ds_cfg["fmt"]
    task = ds_cfg["task"]
    mp = ModelPair(
        mode=mode,
        single=cfg["models"]["single"],
        orchestrator=cfg["models"]["orchestrator"],
        solver=cfg["models"]["solver"],
        max_tokens=cfg["models"]["max_tokens"],
    )
    pipe = Pipeline(arm=arm, fmt=fmt, mp=mp, logger=logger, dataset=ds_name)
    lm = MathEvalsLM(pipeline=pipe)

    print(f"  [{arm} x {ds_name}] task={task} mode={mode} limit={limit}")
    res = simple_evaluate(
        model=lm,
        tasks=[task],
        num_fewshot=cfg.get("num_fewshot", 0),
        limit=limit,
        bootstrap_iters=0,
        log_samples=True,
        apply_chat_template=False,
        task_manager=task_manager,
        verbosity="WARNING",
        confirm_run_unsafe_code=True,
        random_seed=0,
        numpy_random_seed=1234,
        torch_random_seed=1234,
        fewshot_random_seed=1234,
    )

    agg = res["results"].get(task, {})
    samples = res["samples"][task]

    # lm-eval emits one sample dict per (doc x filter). Collapse to one per doc,
    # preferring the strict-match filter.
    by_doc = {}
    for s in samples:
        by_doc.setdefault(s.get("doc_id"), []).append(s)
    collapsed = []
    for did, grp in sorted(by_doc.items(), key=lambda kv: (kv[0] is None, kv[0])):
        pick = next((x for x in grp if x.get("filter") == "strict-match"), grp[0])
        collapsed.append(pick)

    n, native_ok, shared_ok = 0, 0, 0
    for s in collapsed:
        ctx = _context_of(s)
        rec = logger.pop((arm, ds_name, ctx))
        target = s.get("target")
        gold_src = target
        if fmt == "math" and (target is None or target == ""):
            gold_src = s.get("doc", {}).get("answer") or s.get("doc", {}).get("solution")
        gold = extract_gold(gold_src, fmt)
        native = _native_score(s)
        if rec is None:
            rec = logger.new(arm=arm, dataset=ds_name, fmt=fmt,
                             error="no pending record matched context",
                             context=ctx)
        pred = rec.d.get("extracted_answer")
        sc = is_correct(pred, gold, fmt)
        rec.set(gold_raw=gold_src, gold_answer=gold,
                native_metrics=native, native_correct=native.get("exact_match"),
                shared_correct=sc,
                filtered_resps=s.get("filtered_resps"),
                doc_id=s.get("doc_id"))
        logger.commit(rec)
        n += 1
        native_ok += int(bool(native.get("exact_match")))
        shared_ok += int(sc)

    native_em = None
    for k in ("exact_match,strict-match", "exact_match,flexible-extract",
              "exact_match,none", "exact_match"):
        if k in agg:
            native_em = agg[k]
            break
    return {
        "arm": arm, "dataset": ds_name, "task": task, "n": n,
        "native_exact_match": native_em,
        "native_ok_recount": native_ok / n if n else None,
        "shared_exact_match": shared_ok / n if n else None,
        "agg_raw": agg,
    }


def write_table(run_id, rows, cfg, arms, datasets):
    rdir = os.path.join(ROOT, cfg["paths"]["results_dir"], run_id)
    os.makedirs(rdir, exist_ok=True)
    by = {(r["arm"], r["dataset"]): r for r in rows}

    def cell(a, d):
        r = by.get((a, d))
        if not r:
            return "  -  "
        nat = r["shared_exact_match"]
        return f"{nat:.2f} ({r['n']})" if nat is not None else " err "

    lines = [
        f"# Results — run `{run_id}`", "",
        f"- generated: {dt.datetime.now().isoformat(timespec='seconds')}",
        (f"- mode: single | model=`{cfg['models']['single']}`"
         if cfg['models']['mode'] == 'single' else
         f"- mode: two_model | orchestrator=`{cfg['models']['orchestrator']}`"
         f" solver=`{cfg['models']['solver']}`"),
        f"- per-sample log: `logs/{run_id}/samples.jsonl`",
        f"- llm call log:  `logs/{run_id}/llm_calls.jsonl`", "",
        "Cell = shared-extractor exact-match (n items). See JSON for native lm-eval score.",
        "",
        "| arm | " + " | ".join(datasets) + " |",
        "|" + "---|" * (len(datasets) + 1),
    ]
    for a in arms:
        lines.append(f"| {a} | " + " | ".join(cell(a, d) for d in datasets) + " |")
    lines += ["", "## per-cell detail", "",
              "| arm | dataset | task | n | shared_EM | native_EM |",
              "|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(
            f"| {r['arm']} | {r['dataset']} | {r['task']} | {r['n']} | "
            f"{r['shared_exact_match']} | {r['native_exact_match']} |")
    path = os.path.join(rdir, "results_table.md")
    with open(path, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    with open(os.path.join(rdir, "results.json"), "w") as fh:
        json.dump(rows, fh, indent=2, default=str)
    return path


def main():
    cfg = load_config()
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", nargs="*", default=cfg["arms"])
    ap.add_argument("--datasets", nargs="*", default=list(cfg["datasets"]))
    ap.add_argument("--mode", default=cfg["models"]["mode"],
                    choices=["single", "two_model"])
    ap.add_argument("--single", default=cfg["models"]["single"])
    ap.add_argument("--orchestrator", default=cfg["models"]["orchestrator"])
    ap.add_argument("--solver", default=cfg["models"]["solver"])
    ap.add_argument("--limit", type=int, default=cfg["limit"])
    ap.add_argument("--run-id", default=None)
    args = ap.parse_args()

    cfg["models"]["mode"] = args.mode
    cfg["models"]["single"] = args.single
    cfg["models"]["orchestrator"] = args.orchestrator
    cfg["models"]["solver"] = args.solver
    os.environ["MATHEVALS_CODE_TIMEOUT"] = str(cfg["code_execution"]["timeout_seconds"])

    run_id = args.run_id or dt.datetime.now().strftime("%Y%m%d_%H%M%S") + f"_{args.mode}"
    log_dir = os.path.join(ROOT, cfg["paths"]["logs_dir"], run_id)
    logger = SampleLogger(log_dir)

    from lm_eval.tasks import TaskManager
    task_manager = TaskManager(
        include_path=os.path.join(ROOT, "tasks"), verbosity="WARNING")

    rows = []
    for ds_name in args.datasets:
        ds_cfg = cfg["datasets"][ds_name]
        if ds_name == "putnam" and not os.path.exists(
                os.path.join(ROOT, "tasks", "putnam", "putnam_factored.yaml")):
            print(f"  [skip putnam] no tasks/putnam/putnam_factored.yaml "
                  f"(stub — see tasks/putnam/README.md)")
            continue
        for arm in args.arms:
            try:
                rows.append(run_cell(arm, ds_name, ds_cfg, cfg, args.mode,
                                     args.limit, logger, task_manager))
            except Exception as e:  # noqa: BLE001
                import traceback
                traceback.print_exc()
                rows.append({"arm": arm, "dataset": ds_name,
                             "task": ds_cfg["task"], "n": 0,
                             "native_exact_match": None,
                             "shared_exact_match": None,
                             "error": f"{type(e).__name__}: {e}"})

    logger.flush_unmatched()
    path = write_table(run_id, rows, cfg, args.arms, args.datasets)
    print(f"\nresults table: {path}")
    print(f"per-sample log: {os.path.join(log_dir, 'samples.jsonl')}")


if __name__ == "__main__":
    main()
