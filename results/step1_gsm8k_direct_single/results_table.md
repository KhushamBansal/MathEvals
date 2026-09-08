# Results — run `step1_gsm8k_direct_single`

- generated: 2026-09-08T17:32:30
- mode: single | single=`gpt-4o-mini` orch=`gpt-4o-mini` solver=`gpt-4o`
- per-sample log: `logs/step1_gsm8k_direct_single/samples.jsonl`
- llm call log:  `logs/step1_gsm8k_direct_single/llm_calls.jsonl`

Cell = shared-extractor exact-match (n items). See JSON for native lm-eval score.

| arm | gsm8k |
|---|---|
| direct | 0.27 (15) |

## per-cell detail

| arm | dataset | task | n | shared_EM | native_EM |
|---|---|---|---|---|---|
| direct | gsm8k | gsm8k | 15 | 0.26666666666666666 | 0.26666666666666666 |
