"""Per-sample structured logging.

One JSON object per problem, appended to  <logs_dir>/<run_id>/samples.jsonl
Every LLM call is also flattened into        <logs_dir>/<run_id>/llm_calls.jsonl

Logged per sample (spec):
  orchestrator output, every tool call and its result, solver output,
  extracted answer, gold answer  (+ problem, arm, dataset, final string, score).
"""
from __future__ import annotations

import json
import os
import threading


class SampleRecord:
    def __init__(self, **base):
        self.d = dict(base)
        self.d.setdefault("llm_calls", [])
        self.d.setdefault("tool_calls", [])
        self.d.setdefault("orchestrator_output", None)
        self.d.setdefault("solver_output", None)
        self.d.setdefault("extracted_answer", None)
        self.d.setdefault("gold_answer", None)
        self.d.setdefault("final_string", None)
        self.d.setdefault("error", None)

    # the recorder list Chat() appends to
    @property
    def llm_recorder(self):
        return self.d["llm_calls"]

    def add_tool_call(self, tool, tool_input, output, ok=True, seconds=None, extra=None):
        entry = {"tool": tool, "input": tool_input, "output": output, "ok": ok}
        if seconds is not None:
            entry["seconds"] = seconds
        if extra:
            entry.update(extra)
        self.d["tool_calls"].append(entry)
        return entry

    def set(self, **kw):
        self.d.update(kw)


class SampleLogger:
    def __init__(self, run_dir):
        self.run_dir = run_dir
        os.makedirs(run_dir, exist_ok=True)
        self.samples_path = os.path.join(run_dir, "samples.jsonl")
        self.calls_path = os.path.join(run_dir, "llm_calls.jsonl")
        self._lock = threading.Lock()
        self._pending = {}   # context -> SampleRecord, awaiting gold merge

    def new(self, **base) -> SampleRecord:
        return SampleRecord(**base)

    # ---- pending / gold-merge flow -------------------------------------- #
    def hold(self, key, rec: SampleRecord):
        self._pending[key] = rec

    def pop(self, key):
        """Take a held record without committing (run_eval merges gold, then commits)."""
        return self._pending.pop(key, None)

    def flush_unmatched(self):
        """Commit anything never merged (shouldn't normally happen)."""
        for key, rec in list(self._pending.items()):
            rec.set(error=(rec.d.get("error") or "") + " [never merged with gold]")
            self.commit(rec)
            self._pending.pop(key, None)

    def commit(self, rec: SampleRecord):
        with self._lock:
            with open(self.samples_path, "a") as fh:
                fh.write(json.dumps(rec.d, default=str) + "\n")
            with open(self.calls_path, "a") as fh:
                for i, call in enumerate(rec.d["llm_calls"]):
                    flat = {
                        "dataset": rec.d.get("dataset"),
                        "arm": rec.d.get("arm"),
                        "idx": rec.d.get("idx"),
                        "call_index": i,
                        **call,
                    }
                    fh.write(json.dumps(flat, default=str) + "\n")
