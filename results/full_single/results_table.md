# Results — run `full_single`

- generated: 2026-09-08T18:37:25
- mode: single | model=`gpt-4o-mini`
- per-sample log: `logs/full_single/samples.jsonl`
- llm call log:  `logs/full_single/llm_calls.jsonl`

Cell = shared-extractor exact-match (n items). See JSON for native lm-eval score.

| arm | gsm8k | math | svamp |
|---|---|---|---|
| direct | 0.20 (15) | 0.20 (15) | 0.67 (15) |
| cot | 0.87 (15) | 0.80 (15) | 1.00 (15) |
| plan_and_solve | 0.87 (15) | 0.80 (15) | 0.93 (15) |
| pal | 0.93 (15) | 0.73 (15) | 1.00 (15) |
| pot | 0.80 (15) | 0.60 (15) | 0.87 (15) |
| declarative | 0.80 (15) | 0.20 (15) | 0.93 (15) |
| calculator_only | 0.60 (15) | 0.20 (15) | 0.53 (15) |

## per-cell detail

| arm | dataset | task | n | shared_EM | native_EM |
|---|---|---|---|---|---|
| direct | gsm8k | gsm8k | 15 | 0.2 | 0.2 |
| cot | gsm8k | gsm8k | 15 | 0.8666666666666667 | 0.8666666666666667 |
| plan_and_solve | gsm8k | gsm8k | 15 | 0.8666666666666667 | 0.8666666666666667 |
| pal | gsm8k | gsm8k | 15 | 0.9333333333333333 | 0.9333333333333333 |
| pot | gsm8k | gsm8k | 15 | 0.8 | 0.8 |
| declarative | gsm8k | gsm8k | 15 | 0.8 | 0.8 |
| calculator_only | gsm8k | gsm8k | 15 | 0.6 | 0.6 |
| direct | math | hendrycks_math_algebra | 15 | 0.2 | 0.2 |
| cot | math | hendrycks_math_algebra | 15 | 0.8 | 0.6 |
| plan_and_solve | math | hendrycks_math_algebra | 15 | 0.8 | 0.5333333333333333 |
| pal | math | hendrycks_math_algebra | 15 | 0.7333333333333333 | 0.6 |
| pot | math | hendrycks_math_algebra | 15 | 0.6 | 0.5333333333333333 |
| declarative | math | hendrycks_math_algebra | 15 | 0.2 | 0.2 |
| calculator_only | math | hendrycks_math_algebra | 15 | 0.2 | 0.13333333333333333 |
| direct | svamp | svamp | 15 | 0.6666666666666666 | 0.6666666666666666 |
| cot | svamp | svamp | 15 | 1.0 | 1.0 |
| plan_and_solve | svamp | svamp | 15 | 0.9333333333333333 | 0.9333333333333333 |
| pal | svamp | svamp | 15 | 1.0 | 1.0 |
| pot | svamp | svamp | 15 | 0.8666666666666667 | 0.8666666666666667 |
| declarative | svamp | svamp | 15 | 0.9333333333333333 | 0.9333333333333333 |
| calculator_only | svamp | svamp | 15 | 0.5333333333333333 | 0.5333333333333333 |
