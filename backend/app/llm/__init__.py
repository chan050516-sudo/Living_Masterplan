"""B7 — LLM reasoning layer.

This package sits on top of the deterministic engines (B3 / B4 / B6)
and provides the conversational decision interface:

  - tool_service.py      deterministic read tools the LLM may call
  - validator.py         constraint checker for proposed plans
  - orchestrator.py      the four-stage reasoning loop
  - prompts/             prompt templates (markdown)

The design principle: the LLM reasons freely, but the simulation
engine remains the single source of quantitative truth.
"""

__version__ = "0.1.0"