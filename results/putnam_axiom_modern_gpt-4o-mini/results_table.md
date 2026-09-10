# Putnam-AXIOM (paper protocol) — run `putnam_axiom_modern_gpt-4o-mini`

- regenerated: 2026-09-10T21:01:23 (per-problem detail added from logs; scores unchanged)
- task: `putnam_axiom_original_modern`  (verbatim reference task, tasks/putnam_axiom/)
- model: `gpt-4o-mini`  | 4-shot standardized prompt | temperature 0 | max_gen_toks 2048
- grading: paper's `is_equiv` (normalize -> parse_latex -> simplify(diff)==0)
- per-sample log: `logs/putnam_axiom_modern_gpt-4o-mini/samples.jsonl`

| task | model | n | exact_match |
|---|---|---|---|
| putnam_axiom_original_modern | gpt-4o-mini | 15 | 0.1333 (2/15) |

## per-problem

| doc_id | id | gold | pred | correct |
|---|---|---|---|---|
| 0 | 1985_A2 | `2/3` | `1` |  |
| 1 | 1985_A3 | `e^d-1` | `0` |  |
| 2 | 1985_A4 | `87` | `87` | yes |
| 3 | 1985_A5 | `22` | `28` |  |
| 4 | 1985_A6 | `6x^2+5x+1` | `\frac{3}{2}x^2+\frac{7}{2}x+1` |  |
| 5 | 1985_B1 | `3` | `2` |  |
| 6 | 1985_B2 | `101^{99}` | `9901` |  |
| 7 | 1985_B4 | `\frac{4}{\pi^2}` | `\frac{1}{4}` |  |
| 8 | 1985_B5 | `\frac{\sqrt{\pi}}{\sqrt{1985}}e^{-3970}` | `2\sqrt{\frac{2\pi}{3970}}e^{-3970}` |  |
| 9 | 1986_A1 | `18` | `18` | yes |
| 10 | 1986_A2 | `3` | `9` |  |
| 11 | 1986_A3 | `\frac{\pi}{2}` | `\iny` |  |
| 12 | 1986_A4 | `4^n+2\cdot3^n-4\cdot2^n+1` | `3^n+2^n+1\).` |  |
| 13 | 1986_B1 | `\frac{2}{5}` | `\frac{1}{3}` |  |
| 14 | 1986_B2 | `3` | `1` |  |
