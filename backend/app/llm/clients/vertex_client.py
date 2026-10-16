"""Vertex AI client for Gemini 3.8 Flash.

Wraps the google-genai SDK to provide the two methods the orchestrator
expects:

    chat_with_tools(messages, tools) -> {"content": str|None, "tool_calls": list|None}
    chat_json(messages, schema_hint) -> dict

Authentication uses Application Default Credentials. Run
`gcloud auth application-default login` once for local development.
"""
from dotenv import load_dotenv
load_dotenv()

import json
import logging
import os

from google import genai
from google.genai import types

log = logging.getLogger(__name__)


DEFAULT_MODEL = "gemini-3.8-flash"
DEFAULT_LOCATION = "global"


class VertexGeminiClient:
    """
    Client for Gemini 3.8 Flash on Vertex AI.

    Parameters
    ----------
    project : str
        Google Cloud project ID. Falls back to GOOGLE_CLOUD_PROJECT.
    location : str
        Vertex AI location. Use "global" for the lowest pricing.
    model : str
        Model ID. Defaults to gemini-3.8-flash.
    thinking_level : str
        "LOW", "MEDIUM", or "HIGH". Controls reasoning depth.
        Gemini 3.8 Flash does not support "MINIMAL".
    temperature : float
        Sampling temperature. Gemini 3.8 Flash ignores this field;
        reasoning is controlled via thinkingLevel instead.
    """

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

        # The SDK picks up ADC automatically when vertexai=True.
        self.client = genai.Client(
            vertexai=True,
            project=self.project,
            location=self.location,
        )

    # ------------------------------------------------------------------
    # Tool calling
    # ------------------------------------------------------------------

    def chat_with_tools(self, messages: list, tools: list) -> dict:
        """
        Send a conversation with tool definitions. Returns the model's
        response as a normalised dict.
        """
        contents = self._to_contents(messages)
        tool_declarations = self._to_tool_declarations(tools)

        config = types.GenerateContentConfig(
            tools=tool_declarations or None,
            thinking_config=types.ThinkingConfig(
                thinking_level=self._thinking_level_enum(),
            ),
        )

        response = self.client.models.generate_content(
            model=self.model,
            contents=contents,
            config=config,
        )

        return self._normalise_response(response)

    # ------------------------------------------------------------------
    # JSON mode
    # ------------------------------------------------------------------

    def chat_json(self, messages: list, schema_hint: dict) -> dict:
        """
        Ask the model for a JSON object. schema_hint is injected into
        the prompt as a structural guide; the model is instructed to
        return JSON only.
        """
        contents = self._to_contents(messages)
        # Append the schema hint to the last user message.
        if contents:
            hint_text = (
                "\n\nReturn ONLY a JSON object matching this structure:\n"
                + json.dumps(schema_hint, indent=2)
                + "\n\nNo prose outside the JSON object."
            )
            last = contents[-1]
            if isinstance(last, types.Content) and last.parts:
                last.parts.append(types.Part(text=hint_text))

        config = types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(
                thinking_level=self._thinking_level_enum(),
            ),
            response_mime_type="application/json",
        )

        response = self.client.models.generate_content(
            model=self.model,
            contents=contents,
            config=config,
        )

        text = getattr(response, "text", None) or ""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Attempt to extract a JSON object from the text.
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start:end + 1])
                except json.JSONDecodeError:
                    pass
            log.warning("Could not parse JSON from model response: %s", text[:500])
            raise

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
        """
        Convert the orchestrator's message format to google-genai Content.

        Gemini's protocol requires strict alternation between user and
        model roles. When the orchestrator issues N parallel tool calls
        in a single assistant turn, it appends N consecutive `role="tool"`
        messages. Emitting each as its own user Content violates the
        alternation rule and Gemini rejects the request with
        `400 InvalidArgument`.

        To satisfy the protocol we buffer consecutive tool responses and
        flush them as a single user Content containing N FunctionResponse
        parts whenever the next non-tool message arrives.
        """
        contents = []
        pending_tool_responses = []

        def _flush_tool_responses():
            if pending_tool_responses:
                contents.append(types.Content(
                    role="user",
                    parts=pending_tool_responses[:],
                ))
                pending_tool_responses.clear()

        for m in messages:
            role = m.get("role")

            # Any non-tool message breaks a run of tool responses.
            if role != "tool":
                _flush_tool_responses()

            if role == "system":
                # Gemini has no system role in the low-level Content API,
                # so a system message is modelled as a user turn followed
                # by a trivial model acknowledgement.
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
                # Prefer the preserved raw_parts when present: they
                # carry thought_signature bytes required by Gemini 3.8
                # Flash. Fall back to reconstructing from content +
                # tool_calls when raw_parts is absent (older history,
                # stub clients).
                raw = m.get("raw_parts")
                if raw:
                    parts = []
                    for rp in raw:
                        kind = rp.get("kind")
                        sig = rp.get("thought_signature")
                        if kind == "text":
                            parts.append(types.Part(
                                text=rp.get("text", ""),
                                thought_signature=sig,
                            ))
                        elif kind == "function_call":
                            parts.append(types.Part(
                                function_call=types.FunctionCall(
                                    name=rp["name"],
                                    args=rp.get("arguments") or {},
                                ),
                                thought_signature=sig,
                            ))
                        elif kind == "thought":
                            parts.append(types.Part(
                                thought=True,
                                thought_signature=sig,
                            ))
                    contents.append(types.Content(role="model", parts=parts))
                else:
                    parts = []
                    if m.get("content"):
                        parts.append(types.Part(text=m["content"]))
                    for tc in (m.get("tool_calls") or []):
                        parts.append(types.Part(
                            function_call=types.FunctionCall(
                                name=tc["name"],
                                args=tc.get("arguments") or {},
                            ),
                        ))
                    contents.append(types.Content(role="model", parts=parts))

            elif role == "tool":
                # Buffer, do not flush. The batch is flushed either when
                # a non-tool message arrives or at the end of the loop.
                pending_tool_responses.append(types.Part(
                    function_response=types.FunctionResponse(
                        name=m.get("name"),
                        response={"result": m.get("content")},
                    ),
                ))

        # Flush any trailing tool responses.
        _flush_tool_responses()
        return contents

    def _to_tool_declarations(self, tools: list):
        """Convert the orchestrator's tool schema to google-genai Tools."""
        if not tools:
            return None
        declarations = []
        for t in tools:
            declarations.append(types.FunctionDeclaration(
                name=t["name"],
                description=t.get("description", ""),
                parameters=t.get("parameters"),
            ))
        return [types.Tool(function_declarations=declarations)]

    def _normalise_response(self, response) -> dict:
        """
        Convert a GenerateContentResponse to the orchestrator format.

        Gemini 3.8 Flash is a thinking model. Each function_call part
        carries a `thought_signature` — an encrypted representation of
        the model's internal reasoning. When we replay the conversation
        history on the next turn, we MUST return that signature
        verbatim, otherwise the API rejects the request with
        `Function call is missing a thought_signature`.

        We therefore preserve two things per part:
          - the signature bytes, and
          - the ordering of text / function_call / thought parts.

        The orchestrator format is extended with a `raw_parts` list
        that carries everything needed to reconstruct the model turn.
        """
        content = None
        tool_calls = []
        raw_parts = []

        candidate = response.candidates[0] if response.candidates else None
        if candidate and candidate.content and candidate.content.parts:
            for part in candidate.content.parts:
                sig = getattr(part, "thought_signature", None)
                if part.text:
                    content = (content or "") + part.text
                    raw_parts.append({
                        "kind": "text",
                        "text": part.text,
                        "thought_signature": sig,
                    })
                elif part.function_call:
                    tool_calls.append({
                        "id": part.function_call.name,
                        "name": part.function_call.name,
                        "arguments": dict(part.function_call.args or {}),
                        "thought_signature": sig,
                    })
                    raw_parts.append({
                        "kind": "function_call",
                        "name": part.function_call.name,
                        "arguments": dict(part.function_call.args or {}),
                        "thought_signature": sig,
                    })
                else:
                    # Pure thought block (no text, no function call).
                    # Replayed as-is with its signature.
                    raw_parts.append({
                        "kind": "thought",
                        "thought_signature": sig,
                    })

        return {
            "content": content,
            "tool_calls": tool_calls or None,
            "raw_parts": raw_parts or None,
        }