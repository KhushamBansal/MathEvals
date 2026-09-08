"""lm-eval-harness model shim.

Presents the whole orchestrator+solver exchange to lm-eval as a single
`generate_until` response per problem, so every arm is scored by lm-eval's
own task metric with identical extraction.

Used as an already-constructed instance:
    simple_evaluate(model=MathEvalsLM(pipeline), tasks=[...], ...)
"""
from __future__ import annotations

from lm_eval.api.model import LM
from lm_eval.api.registry import register_model


@register_model("mathevals")
class MathEvalsLM(LM):
    def __init__(self, pipeline=None, **kwargs):
        super().__init__()
        self._pipeline = pipeline
        self._kwargs = kwargs

    # generation --------------------------------------------------------- #
    def generate_until(self, requests, disable_tqdm: bool = False):
        out = []
        for req in requests:
            context, _gen_kwargs = req.args
            out.append(self._pipeline.generate(context))
        return out

    # lm-eval also probes this name in some task paths
    def generate_until_multi_round(self, requests):
        raise NotImplementedError("multi-round not used by these tasks")

    # scoring paths we deliberately do not support ---------------------- #
    def loglikelihood(self, requests, disable_tqdm: bool = False):
        raise NotImplementedError(
            "MathEvalsLM is generate-only; all configured tasks use generate_until")

    def loglikelihood_rolling(self, requests, disable_tqdm: bool = False):
        raise NotImplementedError("MathEvalsLM is generate-only")
