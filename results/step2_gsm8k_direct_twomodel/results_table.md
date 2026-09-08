# Results — run `step2_gsm8k_direct_twomodel`

- generated: 2026-09-08T17:34:15
- mode: two_model | orchestrator=`gpt-4o-mini` solver=`gpt-4o-mini`
- per-sample log: `logs/step2_gsm8k_direct_twomodel/samples.jsonl`
- llm call log:  `logs/step2_gsm8k_direct_twomodel/llm_calls.jsonl`

Cell = shared-extractor exact-match (n items). See JSON for native lm-eval score.

| arm | gsm8k |
|---|---|
| direct | 0.20 (15) |

## per-cell detail

| arm | dataset | task | n | shared_EM | native_EM |
|---|---|---|---|---|---|
| direct | gsm8k | gsm8k | 15 | 0.2 | 0.2 |
