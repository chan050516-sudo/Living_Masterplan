"""Structured output schemas for the LLM reasoning layer.

Phase 12 (2026-10-16): the orchestrator was refactored from an
agentic tool-calling loop to a deterministic data-assembly pipeline.

Phase 12b (2026-10-16): removed every `nullable: True` from the
schemas. Gemini's response_schema uses an OpenAPI 3.0 subset that
does NOT support `nullable`. When the SDK encounters an unsupported
keyword, it stalls locally before issuing the HTTP request — which
presents as a multi-minute hang with no httpx log line.

Optional fields are now expressed by omitting them from `required`,
which is the standard OpenAPI way. The Python side must call
`.get(key)` or use a default when reading them back.
"""

# ------------------------------------------------------------------
# Stage 0 — Intent parsing
# ------------------------------------------------------------------

INTENT_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "target_asset_ids": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
            "description": "Asset IDs the user wants to act on.",
        },
        "objective": {
            "type": "STRING",
            "enum": ["financial", "environmental", "social", "balanced"],
        },
        "constraints": {
            "type": "OBJECT",
            "properties": {
                "capex_limit": {"type": "NUMBER"},
                "no_demolition": {"type": "BOOLEAN"},
            },
        },
        "question_text": {"type": "STRING"},
    },
    "required": ["target_asset_ids", "objective", "question_text"],
}


# ------------------------------------------------------------------
# Stage 2 — Proposal
# ------------------------------------------------------------------

PROPOSAL_PARAMETERS_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        # repurpose / new_development
        "to_subtype": {"type": "STRING"},
        "new_capacity": {"type": "INTEGER"},
        "target_gfa_m2": {"type": "NUMBER"},
        "target_units": {"type": "INTEGER"},
        # retrofit
        "energy_efficiency_gain": {"type": "NUMBER"},
        # spatial interventions
        "canopy_boost": {"type": "NUMBER"},
        # delay_development
        "until": {"type": "INTEGER"},
        # optional cost overrides
        "capex_delta_rm": {"type": "NUMBER"},
        "opex_delta_rm": {"type": "NUMBER"},
    },
}


PROPOSAL_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "reasoning_trace": {
            "type": "STRING",
            "description": (
                "Internal reasoning, up to 200 words. Explain what you "
                "concluded from the context and why the plan is what it is."
            ),
        },
        "plan": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "asset_id": {"type": "STRING"},
                    "type": {
                        "type": "STRING",
                        "enum": [
                            "repurpose",
                            "retrofit",
                            "green_corridor",
                            "pedestrian_upgrade",
                            "new_development",
                            "delay_development",
                            "interim_solar_farm",
                        ],
                    },
                    "parameters": PROPOSAL_PARAMETERS_SCHEMA,
                    "rationale": {"type": "STRING"},
                },
                "required": ["asset_id", "type", "parameters", "rationale"],
            },
        },
    },
    "required": ["reasoning_trace", "plan"],
}


# ------------------------------------------------------------------
# Stage 4 — Justification
# ------------------------------------------------------------------

JUSTIFICATION_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "summary": {"type": "STRING"},
        "why_this_plan": {"type": "STRING"},
        "what_simulation_shows": {"type": "STRING"},
        "beyond_the_model": {"type": "STRING"},
        "recommendation": {"type": "STRING"},
    },
    "required": [
        "summary", "why_this_plan",
        "what_simulation_shows", "recommendation",
    ],
}