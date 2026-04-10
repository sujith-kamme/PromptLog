"""
Most basic usage — one function, one decorator.
Run this file to see promptlog in action.

    python examples/basic_decorator.py
    promptlog runs --project movie_app
"""
import promptlog as pl

pl.init(project="movie_app")


def fake_llm(prompt: str) -> str:
    """Simulated LLM response — replace with your actual LLM client."""
    if "masterpiece" in prompt.lower():
        return "POSITIVE"
    if "terrible" in prompt.lower():
        return "NEGATIVE"
    return "NEUTRAL"


@pl.track(model="gpt-4o", temperature=0.1, max_tokens=5)
def classify(review: str) -> str:
    prompt = f"Classify as POSITIVE, NEUTRAL or NEGATIVE.\nReview: {review}"
    pl.log_prompt(prompt)
    output = fake_llm(prompt)
    return output


if __name__ == "__main__":
    r1 = classify("Her is a masterpiece.")
    r2 = classify("This movie was terrible.")
    r3 = classify("It was okay I guess.")

    print(f"Results: {r1}, {r2}, {r3}")
    print()
    print("Runs logged. View them with:")
    print("  promptlog runs --project movie_app")
    print()
    print("Give feedback with:")
    print("  promptlog review --project movie_app")
