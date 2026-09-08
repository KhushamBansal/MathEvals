# MathEvals — baseline evaluation harness for LLM math reasoning

Orchestrator + solver, wrapped so lm-eval-harness sees **one response per problem**
and scores every scaffold identically. `n=15` per dataset — this is a plumbing
test, not a leaderboard. Prompts are not tuned.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
echo 'OPENAI_API_KEY=sk-...' > .env      # chmod 600; gitignored
```

## Run

```bash
source ./.env

# build order:
.venv/bin/python run_eval.py --arms direct --datasets gsm8k --mode single      # step 1
.venv/bin/python verify_extraction.py                                          # gate
.venv/bin/python run_eval.py --arms direct --datasets gsm8k --mode two_model \
    --orchestrator gpt-4o-mini --solver gpt-4o-mini                            # step 2: nothing shifts

# everything (arms x datasets from config.yaml):
.venv/bin/python run_eval.py --mode single --run-id full_single
```

Outputs per run:

| path | contents |
|---|---|
| `logs/<run_id>/samples.jsonl`  | one object per problem: `problem`, `orchestrator_output`, `tool_calls[]` (each tool call + its result), `solver_output`, `extracted_answer`, `gold_answer`, `final_string`, `shared_correct`, `native_metrics`, full `llm_calls[]` |
| `logs/<run_id>/llm_calls.jsonl`| every LLM request/response/usage, flattened |
| `results/<run_id>/results_table.md` | arm × dataset table + pointer to the log |
| `results/<run_id>/results.json` | same, machine-readable |

## Architecture

```
run_eval.py
  └─ for each (arm, dataset):
       ModelPair(mode)                     harness/models.py   orchestrator + solver roles
       Pipeline(arm, fmt, …).generate(ctx) harness/pipeline.py THE generate(prompt)->str interface
         └─ ARMS[arm](problem, mp, rec)    harness/arms.py     the 7 scaffolds
              ├─ mp.orchestrate / mp.solve harness/llm.py      OpenAI chat, temperature 0, retries, recorded
              ├─ run_python(code, timeout) harness/coderun.py  SUBPROCESS, never exec() in-process
              └─ extract_answer(…, fmt)    harness/extract.py  ONE shared extractor, all arms
       MathEvalsLM(pipeline)               harness/lm_wrapper.py  lm-eval model shim (generate_until only)
       lm_eval.simple_evaluate(…)          scores with the task's own metric
       merge gold + native score           harness/samplelog.py   → samples.jsonl
```

`generate(prompt)` returns a single string formatted in the dataset's gold
delimiter (`#### x` for GSM8K/SVAMP, `$x$` + `\boxed{x}` for MATH/Putnam) so
lm-eval's native filter and the shared extractor both read the same answer.

## The 7 arms

| # | arm | scaffold | prompt source |
|---|---|---|---|
| 1 | `direct` | answer only, no reasoning | written here |
| 2 | `cot` | zero-shot "Let's think step by step" (Kojima, 2-stage) | written here |
| 3 | `plan_and_solve` | PS+ trigger (Wang et al. 2023) | written here |
| 4 | `pal` | Python interpreter, `solution()` | **verbatim** `reasoning-machines/pal` `pal/prompt/math_prompts.py` @ `f81ca2a` |
| 5 | `pot` | Program of Thoughts, variable `ans` | **verbatim** `TIGER-AI-Lab/Program-of-Thoughts` `run_gsm8k.py` prompt @ `850399c` |
| 6 | `declarative` | Peano equations → SymPy | **verbatim** `joyheyueya/declarative-math-word-problem` `prompts/declarative_three_shot.py` |
| 7 | `calculator_only` | orchestrator may ONLY emit arithmetic expressions to a calculator tool | written here |

Vendored files live in `harness/vendor_prompts/` with provenance headers.
`declarative_solve.py` is `utils.py` from that repo, unchanged except an added
`import string` (the original relied on a star-import); its `get_final_using_sympy`
runs **inside the subprocess** because the equations are model-generated.

## Answer extraction

`harness/extract.py :: extract_answer(text, fmt, *, from_program=False)` — the
single function every arm calls.

- `fmt="gsm8k"|"svamp"` → last `#### <number>`, else last `= / answer:` number, else last number
- `fmt="math"|"putnam"` → last balanced `\boxed{…}`, else last `$…$`, else "final answer is …"
- `from_program=True` (PAL `solution()`, PoT `ans`, declarative SymPy result) → normalise the computed value
- results are canonicalised so `extract_answer(wrap(x)) == x` (idempotent)

Scoring reports **both** the shared-extractor exact-match (primary, identical
across arms) and lm-eval's **native** task metric. They agree exactly on
GSM8K/SVAMP. On MATH they can diverge: `hendrycks_math`'s `is_equiv` is string
normalisation, ours is numeric-tolerant; and neither extractor handles every
non-numeric MATH answer (intervals, symbolic expressions) — expected at this
scope.

## Datasets (first 15, deterministic order)

| name | task | notes |
|---|---|---|
| `gsm8k` | built-in `gsm8k` | `####` gold |
| `math` | built-in `hendrycks_math_algebra` | MATH has no combined config; algebra is the slice used. Change to another `hendrycks_math_*` in `config.yaml`. Harmless `trust_remote_code` warning from `datasets` 4.x — the dataset loads as Parquet. |
| `svamp` | `tasks/svamp/svamp.yaml` → HF `MU-NLPC/Calc-svamp` | `doc_to_text=question`, `doc_to_target=result`, exact match |
| `putnam` | **STUB** — see `tasks/putnam/README.md` | no canonical "factored-answer subset" dataset; `run_eval.py` skips it until `tasks/putnam/putnam_factored.yaml` exists |

## Code execution safety

`harness/coderun.py` runs generated code as `python -I` in a **new process
group**, with a scrubbed env (no API keys), `cwd` in scratch, and
`subprocess.run(timeout=…)` (default 12s, `config.yaml`). Timeout kills the
group. Nothing is `exec()`'d in-process.
