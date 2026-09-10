#!/usr/bin/env python
"""Putnam-AXIOM, run the paper's own way -- NOT through the 7-arm sweep.

This bypasses harness/ (no orchestrator+solver, no arms, no shared extractor).
It runs the verbatim-vendored reference lm-eval task in tasks/putnam_axiom/
(from EleutherAI/lm-evaluation-harness PR #2946, brando90:final_putnam_axiom_bm
@ 559bd28) directly against an OpenAI chat model:

  - standardized prompt template + 4 fixed few-shot examples (num_fewshot: 4)
  - one generation per problem, temperature 0
  - extraction: last \\boxed{}, else the "Final Answer: ..." sentence
  - grading: normalize_final_answer -> parse_latex both sides ->
             correct iff sympy.simplify(gold - pred) == 0

One deliberate deviation from the reference YAML: it omits `max_gen_toks`, so
lm-eval would cap generations at its 256-token default and truncate almost every
Putnam solution. We override to 2048 so the model can actually finish.

Usage:
  set -a && source ./.env && set +a
  .venv/bin/python run_putnam_axiom.py                       # gpt-4o-mini, all 522
  .venv/bin/python run_putnam_axiom.py --model gpt-4o --limit 25
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))

DEFAULTS = dict(
    task="putnam_axiom_original",   # the "Original" set = full_eval split, 522 problems
    model="gpt-4o-mini",            # matches the project's full_single baseline model
    max_gen_toks=2048,
    num_concurrent=8,
    max_retries=5,
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", default=DEFAULTS["task"],
                    choices=["putnam_axiom_original", "putnam_axiom_original_modern",
                             "putnam_axiom_variations", "putnam_axiom_variations_org",
                             "putnam_axiom"])
    ap.add_argument("--model", default=DEFAULTS["model"])
    ap.add_argument("--limit", type=int, default=None, help="first-N problems (default: all)")
    ap.add_argument("--max-gen-toks", type=int, default=DEFAULTS["max_gen_toks"])
    ap.add_argument("--num-concurrent", type=int, default=DEFAULTS["num_concurrent"])
    ap.add_argument("--run-id", default=None)
    args = ap.parse_args()

    if not os.environ.get("OPENAI_API_KEY"):
        sys.exit("OPENAI_API_KEY not set  (set -a && source ./.env && set +a)")

    from lm_eval import simple_evaluate
    from lm_eval.tasks import TaskManager

    task_manager = TaskManager(
        include_path=os.path.join(ROOT, "tasks"), verbosity="WARNING")

    model_args = (
        f"model={args.model},"
        f"num_concurrent={args.num_concurrent},"
        f"max_retries={DEFAULTS['max_retries']},"
        f"max_gen_toks={args.max_gen_toks},"
        f"tokenized_requests=False,"
        f"tokenizer_backend=None"
    )

    run_id = args.run_id or f"putnam_axiom_{args.model.replace('/', '_')}"
    print(f"[{run_id}] task={args.task} model={args.model} "
          f"limit={args.limit or 'all'} max_gen_toks={args.max_gen_toks}")

    res = simple_evaluate(
        model="openai-chat-completions",
        model_args=model_args,
        tasks=[args.task],
        limit=args.limit,
        num_fewshot=None,          # use the task's own num_fewshot: 4
        bootstrap_iters=0,
        log_samples=True,
        # openai-chat-completions requires this; with no fewshot_as_multiturn the
        # description + 4 shots + question are sent as one user turn -- i.e. the
        # paper's standardized prompt, unchanged.
        apply_chat_template=True,
        task_manager=task_manager,
        verbosity="WARNING",
        gen_kwargs=f"max_gen_toks={args.max_gen_toks},temperature=0",
        random_seed=0,
        numpy_random_seed=1234,
        torch_random_seed=1234,
        fewshot_random_seed=1234,
    )

    agg = res["results"][args.task]
    samples = res["samples"][args.task]
    em = None
    for k in ("exact_match,none", "exact_match", "exact_match,strict-match"):
        if k in agg:
            em = agg[k]
            break
    n_ok = sum(int(s.get("exact_match", 0)) for s in samples)
    n = len(samples)

    log_dir = os.path.join(ROOT, "logs", run_id)
    res_dir = os.path.join(ROOT, "results", run_id)
    os.makedirs(log_dir, exist_ok=True)
    os.makedirs(res_dir, exist_ok=True)

    # per-problem detail, re-deriving the extracted answer with the paper's own
    # extractor so the saved record shows what was compared.
    sys.path.insert(0, os.path.join(ROOT, "tasks", "putnam_axiom"))
    from utils import ground_truth_boxed_answer, get_generated_answer  # noqa: E402

    per_problem = []
    for s in samples:
        resp = s.get("resps") or s.get("filtered_resps")
        txt = resp[0] if isinstance(resp, list) and resp else resp
        txt = txt[0] if isinstance(txt, list) and txt else txt
        try:
            pred = ground_truth_boxed_answer(str(txt))
        except Exception:  # noqa: BLE001
            try:
                pred = get_generated_answer(str(txt))
            except Exception:  # noqa: BLE001
                pred = None
        per_problem.append({
            "doc_id": s.get("doc_id"),
            "id": s.get("doc", {}).get("id"),
            "year": s.get("doc", {}).get("year"),
            "gold": s.get("doc", {}).get("answer"),
            "pred": pred,
            "exact_match": int(s.get("exact_match", 0) or 0),
        })

    with open(os.path.join(log_dir, "samples.jsonl"), "w") as fh:
        for s in samples:
            fh.write(json.dumps({
                "doc_id": s.get("doc_id"),
                "problem": s.get("doc", {}).get("problem"),
                "gold": s.get("doc", {}).get("answer"),
                "resp": (s.get("resps") or s.get("filtered_resps")),
                "exact_match": s.get("exact_match"),
            }, default=str) + "\n")

    lines = [
        f"# Putnam-AXIOM (paper protocol) — run `{run_id}`", "",
        f"- generated: {dt.datetime.now().isoformat(timespec='seconds')}",
        f"- task: `{args.task}`  (verbatim reference task, tasks/putnam_axiom/)",
        f"- model: `{args.model}`  | 4-shot standardized prompt | temperature 0"
        f" | max_gen_toks {args.max_gen_toks}",
        f"- grading: paper's `is_equiv` (normalize -> parse_latex -> simplify(diff)==0)",
        f"- per-sample log: `logs/{run_id}/samples.jsonl`", "",
        "| task | model | n | exact_match |",
        "|---|---|---|---|",
        (f"| {args.task} | {args.model} | {n} | {em:.4f} ({n_ok}/{n}) |"
         if em is not None else
         f"| {args.task} | {args.model} | {n} | n/a |"),
        "", "## per-problem", "",
        "| doc_id | id | gold | pred | correct |",
        "|---|---|---|---|---|",
    ]
    for p in per_problem:
        lines.append(
            f"| {p['doc_id']} | {p['id'] or ''} | `{p['gold']}` | "
            f"`{p['pred']}` | {'yes' if p['exact_match'] else ''} |")
    table_path = os.path.join(res_dir, "results_table.md")
    with open(table_path, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    with open(os.path.join(res_dir, "results.json"), "w") as fh:
        json.dump({"run_id": run_id, "task": args.task, "model": args.model,
                   "n": n, "n_correct": n_ok, "exact_match": em,
                   "agg": agg, "per_problem": per_problem}, fh, indent=2, default=str)

    print("\n".join(lines))
    print(f"\nresults: {table_path}")


if __name__ == "__main__":
    main()
