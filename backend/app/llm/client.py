"""One function for all LLM calls. Switch provider with LLM_PROVIDER in .env."""
import json
import os
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()


def complete_json(system: str, user: str, model_cls: type[BaseModel]) -> BaseModel:
    provider = os.getenv("LLM_PROVIDER", "compat").lower()
    key = os.environ["LLM_API_KEY"]

    if provider == "openai":
        from openai import OpenAI
        r = OpenAI(api_key=key).beta.chat.completions.parse(
            model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            response_format=model_cls,
        )
        return r.choices[0].message.parsed

    if provider == "compat":  # Gemini, Groq, OpenRouter and other OpenAI-compatible services
        from openai import OpenAI
        client = OpenAI(api_key=key, base_url=os.environ["LLM_BASE_URL"])
        schema = json.dumps(model_cls.model_json_schema())
        sys_prompt = (f"{system}\n\nReply with ONLY a JSON object that matches this JSON schema. "
                      f"No markdown, no commentary.\nSCHEMA: {schema}")
        last_err = None
        for _ in range(2):  # one retry if the JSON is invalid
            r = client.chat.completions.create(
                model=os.environ["LLM_MODEL"],
                messages=[{"role": "system", "content": sys_prompt},
                          {"role": "user", "content": user}],
                response_format={"type": "json_object"},
                temperature=0,
            )
            text = r.choices[0].message.content.strip()
            text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            try:
                return model_cls.model_validate_json(text)
            except Exception as e:
                last_err = e
        raise RuntimeError(f"Model did not return valid JSON: {last_err}")

    if provider == "anthropic":
        import anthropic
        r = anthropic.Anthropic(api_key=key).messages.create(
            model=os.getenv("LLM_MODEL", "claude-sonnet-5-5"),
            max_tokens=1000,
            system=system,
            messages=[{"role": "user", "content": user}],
            tools=[{"name": "emit", "description": "Return the structured result.",
                    "input_schema": model_cls.model_json_schema()}],
            tool_choice={"type": "tool", "name": "emit"},
        )
        for block in r.content:
            if block.type == "tool_use":
                return model_cls.model_validate(block.input)
        raise RuntimeError("Model returned no structured output")

    raise ValueError(f"Unknown LLM_PROVIDER: {provider}")