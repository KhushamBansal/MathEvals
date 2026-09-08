"""The seven arms. Same items, same extractor, only the scaffold changes.

Each arm:  run(problem: str, mp: ModelPair, rec: SampleRecord, fmt: str) -> str
returns the BARE answer string (pipeline.generate wraps it into the dataset's
gold delimiter). Each arm fills rec.orchestrator_output / rec.solver_output and
rec.tool_calls, and passes rec.llm_recorder to every model call.

Arms 4 (pal), 5 (pot), 6 (declarative) use prompts vendored verbatim under
harness/vendor_prompts/.  Arms 1-3, 7 use prompts written here.
"""
from __future__ import annotations

import ast
import json
import os
import re

from .coderun import run_python
from .extract import extract_answer
from .vendor_prompts.pal_math_prompts import MATH_PROMPT, MATH_CHAT_BETA_SYSTEM_MESSAGE
from .vendor_prompts.pot_prompt import prompt as POT_PROMPT
from .vendor_prompts.declarative_prompt import DECLARATIVE_THREE_SHOT_AND_PRINCIPLES

CODE_TIMEOUT = float(os.environ.get("MATHEVALS_CODE_TIMEOUT", "12"))
_VENDOR_DIR = os.path.dirname(os.path.abspath(__file__))


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def _answer_instruction(fmt: str) -> str:
    if fmt in ("math", "putnam"):
        return ("Give ONLY the final answer, formatted exactly as it should appear "
                "inside \\boxed{}. Do not include any words.")
    return "Give ONLY the final numeric answer. No words, no units, no explanation."


def _extract_code(text: str) -> str:
    m = re.search(r"```(?:python|py)?\s*\n(.*?)```", text, re.S)
    if m:
        return m.group(1)
    return text


def _last_stdout_line(res: dict):
    out = (res.get("stdout") or "").strip()
    if not out:
        return None
    return out.splitlines()[-1].strip()


def _answer_from_code(res: dict, fmt: str, rec, arm: str):
    """Shared post-processing for pal/pot: parse the printed value, and record a
    solver-failure error (not an extraction bug) when the subprocess broke."""
    if res.get("timed_out"):
        rec.set(error=f"{arm}: generated code timed out after {CODE_TIMEOUT}s")
        return None
    if res.get("returncode") != 0:
        tail = (res.get("stderr") or "").strip().splitlines()[-1:] or [""]
        rec.set(error=f"{arm}: generated code exited {res['returncode']}: {tail[0][:200]}")
        return None
    ans = extract_answer(_last_stdout_line(res), fmt, from_program=True)
    if ans is None:
        rec.set(error=f"{arm}: could not parse a value from "
                      f"{_last_stdout_line(res)!r}")
    return ans


def _finalize_answer(mp, problem, reasoning, rec, fmt):
    """Second-stage extraction call used by cot / plan_and_solve."""
    user = (f"{problem}\n\n{reasoning}\n\n"
            f"Based on the reasoning above, {_answer_instruction(fmt)}")
    out = mp.orchestrate(
        "You extract the final answer from a worked solution.",
        user, recorder=rec.llm_recorder, tag="orchestrator:finalize", max_tokens=64)
    rec.set(orchestrator_output=out)
    return extract_answer(out, fmt)


# --------------------------------------------------------------------------- #
# arm 1: direct answer
# --------------------------------------------------------------------------- #

def run_direct(problem, mp, rec, fmt):
    parsed = mp.orchestrate(
        "You parse math problems.",
        f"{problem}\n\nIn one line, state exactly what quantity the final answer "
        f"must report (and its units, if any). Do not solve it.",
        recorder=rec.llm_recorder, tag="orchestrator:parse", max_tokens=96)
    rec.set(orchestrator_output=parsed)

    solved = mp.solve(
        f"You answer math problems. {_answer_instruction(fmt)}",
        problem, recorder=rec.llm_recorder, tag="solver:direct", max_tokens=64)
    rec.set(solver_output=solved)
    return extract_answer(solved, fmt)


# --------------------------------------------------------------------------- #
# arm 2: zero-shot chain-of-thought  (Kojima et al. 2022, two-stage)
# --------------------------------------------------------------------------- #

def run_cot(problem, mp, rec, fmt):
    reasoning = mp.solve(
        "You are a careful math problem solver.",
        f"{problem}\n\nLet's think step by step.",
        recorder=rec.llm_recorder, tag="solver:cot")
    rec.set(solver_output=reasoning)
    return _finalize_answer(mp, problem, reasoning, rec, fmt)


# --------------------------------------------------------------------------- #
# arm 3: Plan-and-Solve (PS+)  (Wang et al. 2023)
# --------------------------------------------------------------------------- #

PS_PLUS_TRIGGER = (
    "Let's first understand the problem, extract relevant variables and their "
    "corresponding numerals, and make and devise a complete plan. Then, let's "
    "carry out the plan, calculate intermediate variables (pay attention to "
    "correct numerical calculation and commonsense), solve the problem step by "
    "step, and show the answer."
)


def run_plan_and_solve(problem, mp, rec, fmt):
    reasoning = mp.solve(
        "You are a careful math problem solver.",
        f"{problem}\n\n{PS_PLUS_TRIGGER}",
        recorder=rec.llm_recorder, tag="solver:plan_and_solve")
    rec.set(solver_output=reasoning)
    return _finalize_answer(mp, problem, reasoning, rec, fmt)


# --------------------------------------------------------------------------- #
# arm 4: PAL - Program-aided Language models  (prompt vendored verbatim)
# --------------------------------------------------------------------------- #

def run_pal(problem, mp, rec, fmt):
    rec.set(orchestrator_output="[pal] route -> python interpreter, solution()")
    user = MATH_PROMPT.replace("{question}", problem)
    raw = mp.solve(MATH_CHAT_BETA_SYSTEM_MESSAGE, user,
                   recorder=rec.llm_recorder, tag="solver:pal")
    rec.set(solver_output=raw)

    code = _extract_code(raw)
    if "def solution" in code:
        code = code[code.index("def solution"):]
    script = code + "\n\nprint(repr(solution()))\n"
    res = run_python(script, timeout=CODE_TIMEOUT)
    rec.add_tool_call("python", script, res, ok=(res["returncode"] == 0),
                      seconds=res["seconds"])
    return _answer_from_code(res, fmt, rec, "pal")


# --------------------------------------------------------------------------- #
# arm 5: Program of Thoughts  (prompt vendored verbatim)
# --------------------------------------------------------------------------- #

def run_pot(problem, mp, rec, fmt):
    rec.set(orchestrator_output="[pot] route -> python interpreter, variable `ans`")
    user = POT_PROMPT + "\n" + f"Question: {problem}" + "\n" + "# Python code, return ans" + "\n"
    raw = mp.solve("You write Python code to solve math problems. Only write code.",
                   user, recorder=rec.llm_recorder, tag="solver:pot", stop=["\n\n\n"])
    rec.set(solver_output=raw)

    code = _extract_code(raw)
    # PoT continuation stops at a blank-line gap; keep the first code block only
    code = re.split(r"\n\s*\nQuestion:", code)[0]
    script = code + "\n\nprint(repr(ans))\n"
    res = run_python(script, timeout=CODE_TIMEOUT)
    rec.add_tool_call("python", script, res, ok=(res["returncode"] == 0),
                      seconds=res["seconds"])
    return _answer_from_code(res, fmt, rec, "pot")


# --------------------------------------------------------------------------- #
# arm 6: declarative equations + SymPy  (prompt vendored verbatim)
# --------------------------------------------------------------------------- #

_DECL_SCRIPT = r'''
import sys
sys.path.insert(0, {vendor!r})
from vendor_prompts.declarative_solve import (
    reformat_incre_equations, reformat_equations_from_peano, get_final_using_sympy)
eq_list = {eq_list!r}
equations = reformat_equations_from_peano(reformat_incre_equations(eq_list))
print("EQUATIONS:", equations)
print(repr(get_final_using_sympy(equations)))
'''


def run_declarative(problem, mp, rec, fmt):
    user = DECLARATIVE_THREE_SHOT_AND_PRINCIPLES.format(question=problem)
    raw = mp.solve(
        "You solve math word problems in the formal Peano declarative format.",
        user, recorder=rec.llm_recorder, tag="solver:declarative",
        stop=["\n\n\n"], max_tokens=600)
    rec.set(solver_output=raw)

    eq_list = re.findall(r"\[\[.*?\]\]", raw)
    script = _DECL_SCRIPT.format(vendor=_VENDOR_DIR, eq_list=eq_list)
    res = run_python(script, timeout=CODE_TIMEOUT)
    rec.add_tool_call("sympy", {"eq_list": eq_list}, res,
                      ok=(res["returncode"] == 0), seconds=res["seconds"])
    eqs = None
    for line in (res.get("stdout") or "").splitlines():
        if line.startswith("EQUATIONS:"):
            eqs = line[len("EQUATIONS:"):].strip()
    rec.set(orchestrator_output=f"[declarative] equations: {eqs}")

    last = _last_stdout_line(res)
    sentinel = (last or "").strip().strip("'\"")
    # vendored get_final_using_sympy returns these strings (not answers) on failure
    if sentinel in ("invalid equations", "no goal found", "no solution", "bug",
                    "nan", "None") or res.get("timed_out"):
        rec.set(error=f"declarative: solver produced no answer "
                      f"(sympy returned {sentinel!r}"
                      f"{'; timed out' if res.get('timed_out') else ''})")
        return None
    ans = extract_answer(last, fmt, from_program=True)
    if ans is None and not res.get("timed_out"):
        rec.set(error=f"declarative: could not parse sympy output {sentinel!r}")
    return ans


# --------------------------------------------------------------------------- #
# arm 7: calculator-only override
# --------------------------------------------------------------------------- #

_ALLOWED_BINOPS = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow)


def _safe_arith(expr: str) -> float:
    node = ast.parse(expr, mode="eval")

    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return n.value
        if isinstance(n, ast.BinOp) and isinstance(n.op, _ALLOWED_BINOPS):
            return _apply(n.op, ev(n.left), ev(n.right))
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.UAdd, ast.USub)):
            v = ev(n.operand)
            return v if isinstance(n.op, ast.UAdd) else -v
        raise ValueError(f"disallowed expression element: {ast.dump(n)}")

    def _apply(op, a, b):
        if isinstance(op, ast.Pow) and (abs(b) > 1000 or abs(a) > 1e12):
            raise ValueError("exponent out of allowed range for a calculator")
        return {
            ast.Add: lambda: a + b, ast.Sub: lambda: a - b, ast.Mult: lambda: a * b,
            ast.Div: lambda: a / b, ast.FloorDiv: lambda: a // b,
            ast.Mod: lambda: a % b, ast.Pow: lambda: a ** b,
        }[type(op)]()

    return ev(node)


_CALC_SYS = (
    "You are an orchestrator with exactly ONE tool: a four-function calculator "
    "that evaluates a single arithmetic expression (operators + - * / // % ** and "
    "parentheses only; no functions, no variables). You may NOT do arithmetic "
    "yourself. Decompose the problem into an ordered list of calculator "
    "expressions; refer to the result of step k as Rk."
)


def run_calculator_only(problem, mp, rec, fmt):
    user = (
        f"{problem}\n\n"
        "Respond with ONLY a JSON object:\n"
        '{"steps": ["<expr1>", "<expr2>", ...], "answer_step": <1-based index>}\n'
        "Each expr may use plain numbers, the operators + - * / // % ** and "
        "parentheses, and tokens R1, R2, ... referring to earlier step results."
    )
    raw = mp.orchestrate(_CALC_SYS, user, recorder=rec.llm_recorder,
                         tag="orchestrator:calculator_plan")
    rec.set(orchestrator_output=raw, solver_output=None)

    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        rec.set(error="calculator_only: no JSON plan produced")
        return None
    try:
        plan = json.loads(m.group(0))
        steps = list(plan.get("steps", []))
        answer_step = int(plan.get("answer_step", len(steps)))
    except (ValueError, TypeError) as e:
        rec.set(error=f"calculator_only: bad plan JSON: {e}")
        return None

    results = []
    for i, expr in enumerate(steps, 1):
        subst = re.sub(r"R(\d+)",
                       lambda mm: f"({results[int(mm.group(1)) - 1]})"
                       if 0 < int(mm.group(1)) <= len(results) else "R?",
                       str(expr))
        try:
            val = _safe_arith(subst)
            results.append(val)
            rec.add_tool_call("calculator", {"step": i, "expr": expr, "eval": subst},
                              val, ok=True)
        except Exception as e:  # noqa: BLE001
            rec.add_tool_call("calculator", {"step": i, "expr": expr, "eval": subst},
                              str(e), ok=False)
            rec.set(error=f"calculator step {i} failed: {e}")
            return None

    if not results:
        return None
    if not (1 <= answer_step <= len(results)):
        answer_step = len(results)
    return extract_answer(str(results[answer_step - 1]), fmt, from_program=True)


# --------------------------------------------------------------------------- #

ARMS = {
    "direct": run_direct,
    "cot": run_cot,
    "plan_and_solve": run_plan_and_solve,
    "pal": run_pal,
    "pot": run_pot,
    "declarative": run_declarative,
    "calculator_only": run_calculator_only,
}
