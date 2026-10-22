"""Vertex AI client for Gemini 3.8 Flash.

Phase 12 (2026-10-16):
  - Removed agentic tool-calling.
  - `chat_structured` uses server-side `response_schema` for strict
    JSON, but does NOT pass `thinking_config`. Gemini's thinking
    tokens and the CFG JSON grammar conflict on some endpoints: the
    model wants to emit thought text first, the sampler insists the
    first token be `{`, and the request either stalls or errors.
    The `reasoning_trace` field inside PROPOSAL_SCHEMA gives the
    model a place to reason *inside* the JSON, so no server-side
    thinking is needed.
  - Response parsing skips any `thought` parts defensively.
"""

from dotenv import load_dotenv
load_dotenv()

import json
import logging
import os
import re

from google import genai
from google.genai import types

log = logging.getLogger(__name__)


DEFAULT_MODEL = "gemini-3.8-flash"
DEFAULT_LOCATION = "global"


class VertexGeminiClient:
    """Client for Gemini 3.8 Flash on Vertex AI."""

    def __init__(
        self,
        project: str = None,
        location: str = None,
        model: str = None,
        thinking_level: str = "MEDIUM",
        temperature: float = 0.2,
    ):
        self.project = project or os.environ.get("GOOGLE_CLOUD_PROJECT")
        self.location = location or os.environ.get(
            "GOOGLE_CLOUD_LOCATION", DEFAULT_LOCATION,
        )
        self.model = model or DEFAULT_MODEL
        self.thinking_level = thinking_level
        self.temperature = temperature

        if not self.project:
            raise ValueError(
                "project must be provided or GOOGLE_CLOUD_PROJECT must be set"
            )

        self.client = genai.Client(
            vertexai=True,
            project=self.project,
            location=self.location,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def chat_json(self, messages: list, schema_hint: dict, attachments: list = None) -> dict:
        """
        Free-form JSON mode. The schema is injected into the prompt as
        text. Used for intent parsing and justification writing, where
        no server-side schema is needed.

        Thinking is enabled here because there is no JSON grammar to
        conflict with: the model can reason freely, then emit JSON.
        """
        contents = self._to_contents(messages)
        
        # Add attachments (PDFs, images)
        if attachments:
            for file_bytes, mime_type in attachments:
                contents.append(
                    types.Part.from_bytes(data=file_bytes, mime_type=mime_type)
                )
        if contents:
            hint_text = (
                "\n\nReturn ONLY a JSON object matching this structure:\n"
                + json.dumps(schema_hint, indent=2)
                + "\n\nRULES:"
                "\n- No prose. No explanations. No code fences."
                "\n- Start your response with `{` and end with `}`."
                "\n- Every required field must be present."
                "\n- Use null for optional fields you have no value for."
            )
            last = contents[-1]
            if isinstance(last, types.Content) and last.parts:
                last.parts.append(types.Part(text=hint_text))

        config = types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(
                thinking_level=self._thinking_level_enum(),
            ),
        )

        response = self.client.models.generate_content(
            model=self.model,
            contents=contents,
            config=config,
        )

        text = _extract_text_from_response(response)
        return _parse_json_response(text)

    def chat_structured(self, messages: list, response_schema: dict) -> dict:
        """
        Structured output via prompt, not via server-side schema.

        Phase 12c (2026-10-16): we no longer pass `response_schema` to
        the API. The SDK's local schema processing stalls on complex
        nested schemas (arrays of objects with referenced sub-schemas):
        the HTTP request never leaves the client and the call appears
        to hang for minutes.

        We instead:
          1. Serialise the schema to text and append it to the prompt.
          2. Enable `response_mime_type="application/json"` so the
             model is strongly biased toward JSON output.
          3. Set thinking_level=LOW — no schema for thinking tokens
             to interfere with, and no need for heavy reasoning here.
          4. Recover JSON defensively with _parse_json_response.

        The trade-off: schema compliance is enforced by prompt
        discipline, not by constrained decoding. _parse_json_response
        handles fenced and embedded JSON.
        """
        import time as _time

        contents = self._to_contents(messages)

        # Inject the schema as text into the last user message.
        schema_text = (
            "\n\n## Required Output Schema\n\n"
            "Return a JSON object matching this schema EXACTLY:\n\n"
            "```json\n"
            + json.dumps(response_schema, indent=2)
            + "\n```\n\n"
            "RULES:\n"
            "- Return ONLY the JSON object. No prose.\n"
            "- Do NOT wrap your response in code fences.\n"
            "- Include every required field.\n"
            "- Enum fields must use one of the listed values.\n"
        )
        last = contents[-1]
        if isinstance(last, types.Content) and last.parts:
            last.parts.append(types.Part(text=schema_text))

        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            thinking_config=types.ThinkingConfig(
                thinking_level=types.ThinkingLevel.LOW,
            ),
        )

        log.info("Stage 2: sending structured-via-prompt request "
                 "(%d messages)", len(messages))
        t0 = _time.time()
        
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=contents,
                config=config,
            )
        except Exception as e:
            raise

        log.info("Stage 2: returned in %.2fs", _time.time() - t0)
        text = _extract_text_from_response(response)
        log.info("Stage 2: received %d chars", len(text))
        return _parse_json_response(text)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _thinking_level_enum(self):
        level = (self.thinking_level or "MEDIUM").upper()
        mapping = {
            "LOW": types.ThinkingLevel.LOW,
            "MEDIUM": types.ThinkingLevel.MEDIUM,
            "HIGH": types.ThinkingLevel.HIGH,
        }
        return mapping.get(level, types.ThinkingLevel.MEDIUM)

    def _to_contents(self, messages: list) -> list:
        """Convert the orchestrator's message format to google-genai
        Content. No tool-calling, no function_response."""
        contents = []
        for m in messages:
            role = m.get("role")
            if role == "system":
                contents.append(types.Content(
                    role="user",
                    parts=[types.Part(text=m.get("content") or "")],
                ))
                contents.append(types.Content(
                    role="model",
                    parts=[types.Part(text="Understood.")],
                ))
            elif role == "user":
                contents.append(types.Content(
                    role="user",
                    parts=[types.Part(text=m.get("content") or "")],
                ))
            elif role == "assistant":
                contents.append(types.Content(
                    role="model",
                    parts=[types.Part(text=m.get("content") or "")],
                ))
            else:
                log.warning("Unknown message role: %s", role)
        return contents


# ------------------------------------------------------------------
# Response text extraction
# ------------------------------------------------------------------


def _extract_text_from_response(response) -> str:
    """
    Collect text from the response, skipping any `thought` parts.

    When server-side thinking is enabled (chat_json), the response
    contains both a thought part and a text part. The thought part is
    internal reasoning and must not be parsed as JSON.
    """
    if not response or not getattr(response, "candidates", None):
        return ""
    candidate = response.candidates[0]
    if not candidate or not candidate.content:
        return ""

    parts_text = []
    for part in (candidate.content.parts or []):
        # Skip thought parts when present.
        if getattr(part, "thought", False):
            continue
        if part.text:
            parts_text.append(part.text)

    # Fall back to the convenience `.text` attribute if we got nothing.
    if not parts_text:
        fallback = getattr(response, "text", None)
        if fallback:
            return fallback
    return "".join(parts_text)


# ------------------------------------------------------------------
# Tolerant JSON recovery
# ------------------------------------------------------------------

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _parse_json_response(text: str) -> dict:
    """
    Recover a JSON object from a model response.

    Handles:
      1. Clean JSON — the whole response is the object.
      2. Fenced JSON — the object is inside ```json ... ```.
      3. Embedded JSON — the object is surrounded by prose. Scan for
         the outermost balanced {...} block, respecting quoted strings
         and escaped characters.
    """
    if not text:
        raise ValueError("Empty model response")

    # Case 1: clean JSON
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Case 2: fenced JSON
    fence_match = _JSON_FENCE_RE.search(text)
    if fence_match:
        try:
            return json.loads(fence_match.group(1))
        except json.JSONDecodeError:
            pass

    # Case 3: embedded JSON — outermost balanced braces
    start = text.find("{")
    if start >= 0:
        depth = 0
        in_string = False
        escape = False
        for i in range(start, len(text)):
            ch = text[i]
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start:i + 1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        break

    log.warning("Could not parse JSON from model response: %s", text[:500])
    raise ValueError("No valid JSON object found in model response")

def _collect_schema_keys(schema, acc=None):
    """
    Recursively collect every keyword used in a schema dict.

    Used purely for logging: if an illegal keyword like `nullable`
    slips into a schema, this will show it in the log line before the
    request is made.
    """
    if acc is None:
        acc = set()
    if isinstance(schema, dict):
        for k, v in schema.items():
            acc.add(k)
            _collect_schema_keys(v, acc)
    elif isinstance(schema, list):
        for item in schema:
            _collect_schema_keys(item, acc)
    return acc