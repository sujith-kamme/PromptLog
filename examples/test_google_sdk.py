"""
PromptLog + Google Gemini SDK

    uv pip install google-genai python-dotenv
    python examples/test_google_sdk.py
    promptlog runs --project google_sdk
"""
from dotenv import load_dotenv

load_dotenv()

import promptlog as pl
from google import genai

pl.init(project="google_sdk", feedback_mode="end")

client = genai.Client()
PROMPT = "In one sentence, what is the capital of France?"
MODEL = "gemini-2.0-flash"
TEMPERATURE = 0.0


@pl.track(model=MODEL, temperature=TEMPERATURE)
def chat(prompt: str) -> str:
    pl.log_prompt(prompt)
    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config={"temperature": TEMPERATURE},
    )
    return response.text


if __name__ == "__main__":
    result = chat(PROMPT)
    print(result)
    print()
