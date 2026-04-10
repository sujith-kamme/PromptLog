"""
PromptLog + OpenAI SDK

    uv pip install openai python-dotenv
    python examples/test_openai_sdk.py
    promptlog runs --project openai_sdk
"""
from dotenv import load_dotenv

load_dotenv()

import promptlog as pl
from openai import OpenAI

pl.init(project="openai_sdk", feedback_mode="end")

client = OpenAI()
PROMPT = "In one sentence, what is the capital of France?"
MODEL = "gpt-4o-mini"
TEMPERATURE = 0.0


@pl.track(model=MODEL, temperature=TEMPERATURE)
def chat(prompt: str) -> str:
    pl.log_prompt(prompt)
    response = client.chat.completions.create(
        model=MODEL,
        temperature=TEMPERATURE,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content


if __name__ == "__main__":
    result = chat(PROMPT)
    print(result)
    print()
