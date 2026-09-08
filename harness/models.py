"""Orchestrator + Solver roles behind one object.

mode == 'single'   : one model plays both roles (build-order step 1)
mode == 'two_model': orchestrator model parses/routes/formats, solver model
                     does the math or writes the code (build-order step 2+)

Nothing here knows about lm-eval or datasets.
"""
from __future__ import annotations

from .llm import Chat


class ModelPair:
    def __init__(self, mode: str, single: str, orchestrator: str, solver: str,
                 max_tokens: int = 1536):
        self.mode = mode
        self.max_tokens = max_tokens
        if mode == "single":
            self._orch = Chat(single, max_tokens)
            self._solver = self._orch
            self.orchestrator_name = single
            self.solver_name = single
        elif mode == "two_model":
            self._orch = Chat(orchestrator, max_tokens)
            self._solver = Chat(solver, max_tokens)
            self.orchestrator_name = orchestrator
            self.solver_name = solver
        else:
            raise ValueError(f"bad mode {mode!r}")

    def orchestrate(self, system, user, *, recorder, stop=None, tag="orchestrator",
                    max_tokens=None) -> str:
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.append({"role": "user", "content": user})
        return self._orch(msgs, stop=stop, tag=tag, recorder=recorder,
                          max_tokens=max_tokens)

    def solve(self, system, user, *, recorder, stop=None, tag="solver",
              max_tokens=None) -> str:
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.append({"role": "user", "content": user})
        return self._solver(msgs, stop=stop, tag=tag, recorder=recorder,
                            max_tokens=max_tokens)
