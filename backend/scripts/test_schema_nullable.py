"""Prove that `nullable: True` in response_schema stalls the request.

Run from repo root:
    python backend/scripts/test_schema_nullable.py
"""
import os
import time
from google import genai
from google.genai import types

client = genai.Client(
    vertexai=True,
    project=os.environ["GOOGLE_CLOUD_PROJECT"],
    location=os.environ.get("GOOGLE_CLOUD_LOCATION", "global"),
)

# Same shape as PROPOSAL_SCHEMA, but tiny.
schema_with_nullable = {
    "type": "OBJECT",
    "properties": {
        "name": {"type": "STRING", "nullable": True},
        "age": {"type": "INTEGER", "nullable": True},
    },
    "required": ["name"],
}

schema_without_nullable = {
    "type": "OBJECT",
    "properties": {
        "name": {"type": "STRING"},
        "age": {"type": "INTEGER"},
    },
    "required": ["name"],
}

def try_schema(label, schema):
    print(f"\n=== {label} ===")
    print(f"schema: {schema}")
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=schema,
        temperature=0.1,
    )
    t0 = time.time()
    try:
        response = client.models.generate_content(
            model="gemini-3.8-flash",
            contents=[types.Content(
                role="user",
                parts=[types.Part(text="Return {name: 'Alice', age: 30}")],
            )],
            config=config,
        )
        elapsed = time.time() - t0
        print(f"OK in {elapsed:.2f}s: {response.text}")
    except Exception as e:
        elapsed = time.time() - t0
        print(f"FAIL in {elapsed:.2f}s: {type(e).__name__}: {e}")


if __name__ == "__main__":
    try_schema("With nullable", schema_with_nullable)
    try_schema("Without nullable", schema_without_nullable)