"""Structured output schemas for the LLM reasoning layer.

Phase 13 (2026-10-17):
  - P0 — Multi-candidate generation. The LLM now produces 2-3
    complete candidate plans (CANDIDATES_SCHEMA), each of which is
    validated and simulated. A second LLM call picks the winner
    from the simulation results (SELECTION_SCHEMA).
  - P1 — Retrofit measure breakdown. `measure_breakdown` allows
    per-measure capex / energy_gain / affected subsystems. The
    engine applies per-subsystem multipliers when it is present,
    and falls back to the aggregate `energy_efficiency_gain` when
    it is not.
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
# Stage 2 — Parameters (shared by candidates and final plan)
# ------------------------------------------------------------------

PROPOSAL_PARAMETERS_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        # --- repurpose / new_development ---
        "to_subtype": {"type": "STRING"},
        "new_capacity": {"type": "INTEGER"},
        "target_gfa_m2": {"type": "NUMBER"},
        "target_units": {"type": "INTEGER"},

        # --- retrofit (P1: measure_breakdown added) ---
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
        "measure_breakdown": {
            "type": "ARRAY",
            "description": (
                "Optional detailed breakdown of each retrofit measure. "
                "When present, the engine applies energy gains per "
                "subsystem instead of a global multiplier. Each entry "
                "must correspond to one name in `measures`."
            ),
            "items": {
                "type": "OBJECT",
                "properties": {
                    "name": {"type": "STRING"},
                    "capex_rm": {"type": "NUMBER"},
                    "energy_gain": {"type": "NUMBER"},
                    "affected": {
                        "type": "ARRAY",
                        "items": {
                            "type": "STRING",
                            "enum": [
                                "hvac",
                                "lighting_equipment",
                                "base_load",
                            ],
                        },
                    },
                },
                "required": ["name", "capex_rm", "energy_gain", "affected"],
            },
        },

        # --- spatial interventions ---
        "canopy_boost": {"type": "NUMBER"},

        # --- delay_development ---
        "until": {"type": "INTEGER"},

        # --- design-layer fields ---
        "scale": {"type": "STRING", "enum": ["small", "medium", "large"]},
        "target_demographic": {"type": "STRING"},
        "program_mix": {"type": "ARRAY", "items": {"type": "STRING"}},
        "design_notes": {"type": "STRING"},

        # --- optional cost overrides ---
        "capex_delta_rm": {"type": "NUMBER"},
        "opex_delta_rm": {"type": "NUMBER"},
    },
}


# ------------------------------------------------------------------
# Reusable plan item (one intervention on one asset)
# ------------------------------------------------------------------

_PLAN_ITEM_SCHEMA = {
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
        "investment_case": {
            "type": "OBJECT",
            "properties": {
                "capital_invested": {"type": "STRING"},
                "return_delivered": {"type": "STRING"},
                "strategic_rationale": {"type": "STRING"},
            },
            "required": [
                "capital_invested",
                "return_delivered",
                "strategic_rationale",
            ],
        },
    },
    "required": ["asset_id", "type", "parameters", "rationale"],
}


# ------------------------------------------------------------------
# Stage 2 — Candidate generation (P0)
# ------------------------------------------------------------------

CANDIDATES_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "reasoning_trace": {
            "type": "STRING",
            "description": (
                "Your strategic overview, up to 250 words. Explain how "
                "you read the three capitals, what the deadspace gap "
                "is, and what axes of variation distinguish the "
                "candidates you are about to produce."
            ),
        },
        "candidates": {
            "type": "ARRAY",
            "description": (
                "Two or three COMPLETE candidate plans. Each candidate "
                "must cover every target asset. Candidates must differ "
                "meaningfully in their strategy — not three flavours of "
                "the same idea. At least one candidate should be a "
                "bold move (repurpose / new_development); at least one "
                "may be incremental (retrofit / upgrade)."
            ),
            "items": {
                "type": "OBJECT",
                "properties": {
                    "name": {
                        "type": "STRING",
                        "description": (
                            "A short strategy label, e.g. "
                            "'Full repurpose', 'Cost recovery', "
                            "'Mixed-use intervention'."
                        ),
                    },
                    "strategy_summary": {
                        "type": "STRING",
                        "description": (
                            "One sentence explaining what this "
                            "candidate is trying to achieve."
                        ),
                    },
                    "reasoning_trace": {
                        "type": "STRING",
                        "description": (
                            "Why this candidate makes sense, up to "
                            "120 words."
                        ),
                    },
                    "plan": {
                        "type": "ARRAY",
                        "items": _PLAN_ITEM_SCHEMA,
                    },
                },
                "required": ["name", "strategy_summary", "plan"],
            },
        },
    },
    "required": ["reasoning_trace", "candidates"],
}


# ------------------------------------------------------------------
# Stage 2.7 — Final selection (P0)
# ------------------------------------------------------------------

SELECTION_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "selected_candidate_name": {
            "type": "STRING",
            "description": (
                "The exact `name` of the candidate you selected from "
                "the list of simulated candidates."
            ),
        },
        "selection_reasoning": {
            "type": "STRING",
            "description": (
                "Why this candidate beats the others, up to 150 words. "
                "Reference concrete numbers from the simulation briefs."
            ),
        },
        "key_trade_offs": {
            "type": "ARRAY",
            "description": (
                "Two to four trade-offs the selected candidate makes "
                "relative to the alternatives. Each entry is one "
                "sentence."
            ),
            "items": {"type": "STRING"},
        },
    },
    "required": ["selected_candidate_name", "selection_reasoning"],
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