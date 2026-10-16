"""Structured output schemas for the LLM reasoning layer.

Phase 12 (2026-10-16): the orchestrator was refactored from an
agentic tool-calling loop to a deterministic data-assembly pipeline.

Phase 12b: removed every `nullable: True` from the schemas. Gemini's
response_schema uses an OpenAPI 3.0 subset that does NOT support
`nullable`. Optional fields are expressed by omitting them from
`required`.

Phase 13 (2026-10-16): widened the solution space. Every intervention
now carries a `design_notes` field for free-form implementation
detail, plus structured design fields (scale, target_demographic,
program_mix) that are NOT consumed by the engine but ARE shown in the
justification and user-facing report. `retrofit` additionally gains
a `measures` array listing the physical upgrades applied.
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

# The `parameters` object is intentionally wide: different intervention
# types use different keys. The engine only consumes a subset
# (to_subtype, new_capacity, target_gfa_m2, until, measures,
# energy_efficiency_gain, canopy_boost). The rest are design-layer
# fields that flow through to the justification and the user-facing
# report without touching the simulation.
PROPOSAL_PARAMETERS_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        # --- repurpose / new_development ---
        "to_subtype": {"type": "STRING"},
        "new_capacity": {"type": "INTEGER"},
        "target_gfa_m2": {"type": "NUMBER"},
        "target_units": {"type": "INTEGER"},

        # --- retrofit (new) ---
        "energy_efficiency_gain": {"type": "NUMBER"},
        "measures": {
            "type": "ARRAY",
            "items": {
                "type": "STRING",
                "enum": [
                    "hvac_upgrade",
                    "led_lighting",
                    "building_envelope",
                    "cool_roof",
                    "bms_controls",
                    "water_efficiency",
                ],
            },
        },

        # --- spatial interventions ---
        "canopy_boost": {"type": "NUMBER"},

        # --- delay_development ---
        "until": {"type": "INTEGER"},

        # --- design-layer fields (not consumed by the engine) ---
        "scale": {
            "type": "STRING",
            "enum": ["small", "medium", "large"],
        },
        "target_demographic": {"type": "STRING"},
        "program_mix": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
        },
        "design_notes": {
            "type": "STRING",
            "description": (
                "Free-form implementation detail. Use for anything the "
                "schema does not cover: phasing, amenities, specific "
                "materials, site constraints, operational sequencing. "
                "This text is shown to the user and quoted in the "
                "justification, but is NOT consumed by the simulation."
            ),
        },

        # --- optional cost overrides ---
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
                "Your strategic reasoning, up to 300 words. Walk through: "
                "(a) what the diagnosis is telling you, (b) at least THREE "
                "candidate interventions you considered, (c) the trade-off "
                "that decided between them, (d) why the chosen plan is the "
                "best fit for the user's objective."
            ),
        },
        "alternatives_considered": {
            "type": "ARRAY",
            "description": (
                "Two or three other interventions you seriously evaluated "
                "and rejected. This is how the user sees your reasoning. "
                "For each: what it was, and the specific reason you did "
                "not choose it (cost, competition overlap, wrong "
                "demographic, insufficient impact, etc.)."
            ),
            "items": {
                "type": "OBJECT",
                "properties": {
                    "asset_id": {"type": "STRING"},
                    "type": {"type": "STRING"},
                    "summary": {"type": "STRING"},
                    "rejected_because": {"type": "STRING"},
                },
                "required": ["asset_id", "type", "summary", "rejected_because"],
            },
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
    "required": ["reasoning_trace", "alternatives_considered", "plan"],
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