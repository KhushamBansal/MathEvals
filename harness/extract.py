"""The ONE shared answer-extraction + matching module.

Every arm (direct, cot, plan_and_solve, pal, pot, declarative, calculator_only)
routes its final answer through `extract_answer()` here. Nothing else extracts.

Sources it must handle (per spec):
  - GSM8K  -> answer marked with '####'
  - MATH   -> answer in '\\boxed{...}'
  - PAL / PoT / declarative -> the value returned by executed code (solution()/ans)
  - calculator_only -> a numeric string produced by the calculator tool

Public API:
  extract_answer(text, fmt, *, from_program=False) -> str | None
  normalize_numeric(s) -> str | None
  is_correct(pred, gold, fmt) -> bool
  extract_gold(raw, fmt) -> str          # normalise a dataset's gold field
"""
from __future__ import annotations

import re
from fractions import Fraction

# ---------------------------------------------------------------------------
# numeric normalisation
# ---------------------------------------------------------------------------

_NUM_RE = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


def normalize_numeric(s):
    """Return a canonical numeric string, or None if `s` is not numeric.

    '1,234' -> '1234'   '3.50' -> '3.5'   '7.0' -> '7'   '$-2' -> '-2'
    '1/2' -> '0.5'      '  8 ' -> '8'
    """
    if s is None:
        return None
    t = str(s).strip()
    if not t:
        return None
    t = t.replace("$", "").replace("%", "").replace("\\%", "")
    t = t.replace(",", "").replace(" ", "").replace("\\!", "").replace("\\,", "")
    t = t.strip("=")
    # strip parens wrapping a bare number: '(-2)/(3)' or '-(2)/(3)' -> '-2/3'
    for _ in range(3):
        t = re.sub(r"\((-?\d+(?:\.\d+)?)\)", r"\1", t)
    # bare fraction a/b
    m = re.fullmatch(r"(-?\d+)\s*/\s*(-?\d+)", t)
    if m:
        try:
            t = str(float(Fraction(int(m.group(1)), int(m.group(2)))))
        except ZeroDivisionError:
            return None
    try:
        f = float(t)
    except ValueError:
        return None
    if f != f or f in (float("inf"), float("-inf")):
        return None
    if abs(f - round(f)) < 1e-9:
        return str(int(round(f)))
    # trim floating noise, drop trailing zeros
    return ("%.10f" % f).rstrip("0").rstrip(".")


# ---------------------------------------------------------------------------
# \boxed{...} handling (balanced braces)
# ---------------------------------------------------------------------------

def _last_boxed(text):
    idx = text.rfind("\\boxed")
    if idx < 0:
        idx = text.rfind("\\fbox")
    if idx < 0:
        return None
    i = idx
    while i < len(text) and text[i] != "{":
        # support "\boxed 5" form
        if text[i] == " " and i > idx + 5:
            rest = text[i + 1 :].strip().split()
            return rest[0] if rest else None
        i += 1
    if i >= len(text):
        return None
    depth = 0
    start = i
    for j in range(i, len(text)):
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1 : j]
    return None


# light LaTeX normalisation for non-numeric MATH/Putnam answers
def _normalize_latex(s):
    s = s.strip()
    s = s.replace("\\left", "").replace("\\right", "")
    s = s.replace("\\dfrac", "\\frac").replace("\\tfrac", "\\frac")
    s = s.replace("\\!", "").replace("\\,", "").replace("\\;", "").replace("\\ ", "")
    s = s.replace("\\$", "").replace("$", "")
    s = re.sub(r"\\text\{([^}]*)\}", r"\1", s)
    s = s.replace(" ", "")
    s = s.rstrip(".")
    if s.startswith("{") and s.endswith("}"):
        s = s[1:-1]
    # \frac{a}{b} -> a/b
    s = re.sub(r"\\frac\{([^{}]+)\}\{([^{}]+)\}", r"(\1)/(\2)", s)
    return s


def _canon_math(s):
    """Idempotent canonical form for a MATH/Putnam answer: numeric if possible,
    else LaTeX-normalised text. extract_answer(wrap(x)) must equal x."""
    if s is None:
        return None
    lx = _normalize_latex(str(s))
    n = normalize_numeric(lx)
    return n if n is not None else lx


# ---------------------------------------------------------------------------
# the shared extractor
# ---------------------------------------------------------------------------

def extract_answer(text, fmt, *, from_program=False):
    """Pull the final answer string out of `text`.

    fmt          : 'gsm8k' | 'svamp' | 'math' | 'putnam'
    from_program : True when `text` is the stringified return value of executed
                   code (PAL solution(), PoT ans, declarative sympy result).
    """
    if text is None:
        return None
    text = str(text)

    if from_program:
        # code already computed the value; just normalise it
        stripped = text.strip().strip("'\"")
        if fmt in ("gsm8k", "svamp"):
            return normalize_numeric(stripped)
        return _canon_math(stripped) or None

    if fmt in ("gsm8k", "svamp"):
        m = list(re.finditer(r"####\s*(-?[\d\.,/]+)", text))
        if m:
            return normalize_numeric(m[-1].group(1))
        m = list(re.finditer(r"(?:final answer|answer|=)\D{0,8}(-?\$?\d[\d,]*(?:\.\d+)?)",
                             text, re.I))
        if m:
            return normalize_numeric(m[-1].group(1))
        nums = _NUM_RE.findall(text)
        return normalize_numeric(nums[-1]) if nums else None

    if fmt in ("math", "putnam"):
        boxed = _last_boxed(text)
        if boxed is not None:
            return _canon_math(boxed)
        # fall back to $...$ (hendrycks_math style) then "final answer is X"
        dollars = re.findall(r"\$(.+?)\$", text, re.S)
        if dollars:
            return _canon_math(dollars[-1])
        m = re.search(r"final answer is\s*:?\s*(.+?)(?:\.|\n|$)", text, re.I)
        if m:
            return _canon_math(m.group(1).strip())
        nums = _NUM_RE.findall(text)
        return normalize_numeric(nums[-1]) if nums else None

    raise ValueError(f"unknown fmt: {fmt!r}")


def extract_gold(raw, fmt):
    """Normalise a dataset's raw gold field into the same space as extract_answer."""
    if fmt in ("gsm8k",):
        after = str(raw).split("####")[-1]
        return normalize_numeric(after)
    if fmt in ("svamp",):
        n = normalize_numeric(raw)
        return n if n is not None else str(raw).strip()
    if fmt in ("math", "putnam"):
        # gold may be a bare answer or a full solution containing \boxed{}
        boxed = _last_boxed(str(raw))
        return _canon_math(boxed if boxed is not None else str(raw))
    raise ValueError(f"unknown fmt: {fmt!r}")


def is_correct(pred, gold, fmt):
    if pred is None or gold is None:
        return False
    pc, gc = _canon_math(pred), _canon_math(gold)
    try:
        return abs(float(pc) - float(gc)) <= 1e-6
    except (ValueError, TypeError):
        pass
    return pc == gc
