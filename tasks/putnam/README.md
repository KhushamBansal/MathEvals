# Putnam task — STUB (needs a dataset decision)

Spec: *"Putnam: factored-answer subset only, answer-matched not proof-checked."*

There is no single canonical HF dataset for a "factored-answer subset" of Putnam.
Candidates:

| Source | Notes |
|---|---|
| `Putnam-AXIOM` (Original) | Competition problems with `\boxed{}` final answers. Would need filtering to the subset whose answer is a closed-form / factored expression. Answer-matched. |
| `PutnamBench` | Formal (Lean/Isabelle/Coq) **proof** benchmark — *not* answer-matched. Does not fit. |
| Hand-curated subset | Pull the ~firsts from Putnam-AXIOM, keep items whose gold answer is a factored expression, commit as a local JSONL. |

`run_eval.py` skips `putnam` unless `putnam_factored.yaml` exists here (rename
`putnam_factored.yaml.disabled` once the dataset is chosen). The YAML template
below already wires `fmt: putnam` (→ `\boxed{}` extraction, `_normalize_latex`
matching in `harness/extract.py`). Fill `dataset_path` / `test_split` and, if the
factored-answer filter is a row predicate, add a `process_docs` function.
