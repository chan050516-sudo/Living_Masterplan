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
        "subtype_changes": {
            "type": "ARRAY",
            "description": (
                "Partial repurpose of a mixed-use asset. Each entry "
                "converts one subtype's area into another subtype "
                "WITHIN THE SAME asset_class. Use this instead of "
                "`to_subtype` when only SOME subtypes of a mixed-use "
                "asset are dead. The healthy subtypes NOT listed here "
                "are preserved untouched. Do NOT combine with "
                "`to_subtype` — if subtype_changes is present, "
                "to_subtype is ignored."
            ),
            "items": {
                "type": "OBJECT",
                "properties": {
                    "from_subtype": {
                        "type": "STRING",
                        "description": (
                            "Subtype to convert FROM. Must be an "
                            "existing key in the asset's unit_mix."
                        ),
                    },
                    "to_subtype": {
                        "type": "STRING",
                        "description": (
                            "Subtype to convert TO. Must be a "
                            "taxonomy subtype in the SAME "
                            "asset_class as from_subtype."
                        ),
                    },
                    "area_m2": {
                        "type": "NUMBER",
                        "description": (
                            "Optional. If absent, the ENTIRE area "
                            "of from_subtype is converted. If "
                            "present, must be positive and <= the "
                            "current area of from_subtype."
                        ),
                    },
                },
                "required": ["from_subtype", "to_subtype"],
            },
        },
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
                "repurpose", "retrofit", "renovation",
                "green_corridor", "pedestrian_upgrade",
                "new_development", "delay_development",
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


# ------------------------------------------------------------------
# Catalytic link — structured causal claim
# ------------------------------------------------------------------
# Phase 15 (2026-10-17): a catalytic intervention acts on one asset
# (acting_on) to benefit another (beneficiary). Every catalytic link
# carries a mechanism and a verification_level. The verification
# level is set by the LLM to reflect what the deterministic
# simulation can actually measure:
#
#   verified           — B4 re-computes the beneficiary's metric and
#                        the delta is visible in comparison.per_asset
#   partially_verified — B4 measures a proxy, but the causal step to
#                        the beneficiary requires assumptions
#   claimed            — B4 cannot measure the effect; the
#                        intervention is offered as an informed
#                        hypothesis, not a simulated outcome
#
# The validator enforces the following caps:
#
#   walkability_improvement  → may be verified
#   catchment_growth         → may be verified (if the delivering
#                              intervention is new_development)
#   competition_relief       → may be partially_verified
#   complementary_use        → may be claimed only
#   footfall_injection       → may be claimed only
#
# An LLM that labels a footfall_injection as "verified" is claiming
# more than the simulation can support; the validator downgrades it
# to "claimed" and records a warning.

CATALYTIC_LINK_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "acting_on_asset_id": {
            "type": "STRING",
            "description": (
                "The asset the intervention physically acts on. "
                "For a catalytic intervention this is NOT the "
                "beneficiary."
            ),
        },
        "beneficiary_asset_id": {
            "type": "STRING",
            "description": (
                "The target asset this catalytic intervention is "
                "intended to benefit. MUST be one of "
                "context_pack.targets."
            ),
        },
        "mechanism": {
            "type": "STRING",
            "enum": [
                "walkability_improvement",
                "catchment_growth",
                "competition_relief",
                "complementary_use",
                "footfall_injection",
            ],
            "description": (
                "walkability_improvement — spatial intervention that "
                "raises the beneficiary's walking coverage\n"
                "catchment_growth        — new residents within the "
                "beneficiary's walking catchment raise demand\n"
                "competition_relief      — reduces direct competitive "
                "pressure on the beneficiary's subtype pool\n"
                "complementary_use       — a nearby use attracts "
                "customers who also consume at the beneficiary\n"
                "footfall_injection      — an anchor use draws "
                "visitors to the area"
            ),
        },
        "verification_level": {
            "type": "STRING",
            "enum": ["verified", "partially_verified", "claimed"],
            "description": (
                "How much of this causal chain the simulation can "
                "actually measure. See the vocabulary at the top of "
                "the prompt. Do not overclaim: if B4 cannot compute "
                "the delta, use 'claimed'."
            ),
        },
        "explanation": {
            "type": "STRING",
            "description": (
                "One sentence describing the causal chain from the "
                "intervention to the beneficiary. Must be concrete: "
                "name the quantity that changes, not just the hope."
            ),
        },
    },
    "required": [
        "acting_on_asset_id",
        "beneficiary_asset_id",
        "mechanism",
        "verification_level",
        "explanation",
    ],
}


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
        "role": {
            "type": "STRING",
            "enum": ["primary", "catalytic"],
            "description": (
                "primary   — acts on a target asset.\n"
                "catalytic — acts on a nearby asset or the network "
                "to benefit a target. Requires `catalytic_link`."
            ),
        },
        "catalytic_link": CATALYTIC_LINK_SCHEMA,
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
    "required": ["asset_id", "type", "role", "parameters", "rationale"],
}


# ------------------------------------------------------------------
# Stage 2.7 — Final Selection & Justification (Merged)
# ------------------------------------------------------------------
FINAL_DECISION_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "selected_candidate_name": {
            "type": "STRING",
            "description": "The exact `name` of the winning candidate."
        },
        "selection_reasoning": {
            "type": "STRING",
            "description": (
                "Internal logic. Up to 150 words. Explain why this candidate "
                "won and why the runner-up lost. Cite concrete numbers."
            ),
        },
        "key_trade_offs": {
            "type": "ARRAY",
            "description": "Two to four one-sentence trade-offs the winner makes.",
            "items": {"type": "STRING"},
        },
        "executive_summary": {
            "type": "STRING",
            "description": "One paragraph a board member can absorb. What is proposed and the net effect across capitals."
        },
        "why_this_plan": {
            "type": "STRING",
            "description": "Up to 110 words. Strategic rationale, referencing rejected alternatives."
        },
        "what_simulation_shows": {
            "type": "STRING",
            "description": "Up to 120 words. Reference concrete metrics (NOI, carbon, coverage, occupancy). Include trade-offs."
        },
        "beyond_the_model": {
            "type": "STRING",
            "description": "Optional. Up to 60 words. Domain insight beyond the metrics."
        },
        "recommendation": {
            "type": "STRING",
            "description": "One sentence. Under what conditions should the user proceed?"
        },
    },
    "required": [
        "selected_candidate_name", "selection_reasoning", "key_trade_offs",
        "executive_summary", "why_this_plan", "what_simulation_shows", "recommendation"
    ],
}