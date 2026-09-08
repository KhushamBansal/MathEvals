"""The single unified interface.

`Pipeline.generate(context) -> str` runs the full orchestrator+solver exchange
for one problem under the configured arm and returns ONE string, formatted in the
dataset's gold delimiter so lm-eval scores every arm identically.

Records are held pending (keyed by context) until run_eval merges the gold answer
and native score, then committed to samples.jsonl.
"""
from __future__ import annotations

from .arms import ARMS
from .extract import extract_answer

_PREFIXES = ("Question:", "Problem:", "Q:")
_SUFFIXES = ("\nAnswer:", "\nSolution:", "Answer:", "Solution:")


def strip_scaffold(context: str) -> str:
    t = context.strip()
    for p in _PREFIXES:
        if t.startswith(p):
            t = t[len(p):].lstrip()
            break
    for s in _SUFFIXES:
        if t.endswith(s):
            t = t[: -len(s)].rstrip()
            break
    return t


NO_ANSWER = "no answer produced"  # contains no digit / $ / #### / \boxed -> extracts to None


def wrap_final(bare, fmt: str) -> str:
    """Format the bare answer so BOTH lm-eval's native filter and our shared
    extractor can read it back. A None answer wraps to a string that
    re-extracts to None (keeps extract_answer(wrap(x)) == x idempotent)."""
    if bare is None:
        return NO_ANSWER
    if fmt in ("gsm8k", "svamp"):
        return f"#### {bare}"
    # math / putnam: $...$ for hendrycks_math process_results, \boxed{} for us
    return f"The final answer is ${bare}$.\n\\boxed{{{bare}}}"


class Pipeline:
    def __init__(self, arm, fmt, mp, logger, dataset):
        self.arm = arm
        self.fmt = fmt
        self.mp = mp
        self.logger = logger
        self.dataset = dataset
        self._n = 0

    def generate(self, context: str) -> str:
        self._n += 1
        idx = self._n
        problem = strip_scaffold(context)
        rec = self.logger.new(
            dataset=self.dataset, arm=self.arm, fmt=self.fmt, idx=idx,
            model_mode=self.mp.mode,
            orchestrator_model=self.mp.orchestrator_name,
            solver_model=self.mp.solver_name,
            context=context, problem=problem)
        try:
            bare = ARMS[self.arm](problem, self.mp, rec, self.fmt)
        except Exception as e:  # noqa: BLE001 - never let one sample kill the run
            rec.set(error=f"{type(e).__name__}: {e}")
            bare = None
        rec.set(extracted_answer=bare)
        final = wrap_final(bare, self.fmt)
        rec.set(final_string=final)
        # sanity: our own extractor must round-trip what we just wrapped
        rec.set(reextracted=extract_answer(final, self.fmt))
        self.logger.hold((self.arm, self.dataset, context), rec)
        return final
