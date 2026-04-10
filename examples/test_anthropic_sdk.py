"""
PromptLog + Anthropic SDK

    uv pip install anthropic python-dotenv
    python examples/test_anthropic_sdk.py
    promptlog runs --project anthropic_sdk
"""
from dotenv import load_dotenv

load_dotenv()

import anthropic
import promptlog as pl

pl.init(project="anthropic_sdk", feedback_mode="end")

client = anthropic.Anthropic()
PROMPT = "In one sentence, what is the capital of France?"
MODEL = "claude-haiku-4-5-20251001"
TEMPERATURE = 0.0


@pl.track(model=MODEL, temperature=TEMPERATURE)
def chat(prompt: str) -> str:
    pl.log_prompt(prompt)
    response = client.messages.create(
        model=MODEL,
        temperature=TEMPERATURE,
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


if __name__ == "__main__":
    result = chat(PROMPT)
    print(result)
    print()
