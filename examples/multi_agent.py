"""
Multi-agent pipeline example.
Three agents run in sequence. Review all runs at the end via feedback_mode="end".

    python examples/multi_agent.py
"""
import promptlog as pl

pl.init(project="quant_pipeline", feedback_mode="end")


def fake_llm(_prompt: str) -> str:
    """Simulated LLM response — replace with your actual LLM client."""
    return "Simulated output"


@pl.track(model="gpt-4o", temperature=0.7)
def market_agent(sector: str) -> str:
    prompt = f"Identify alpha themes in the {sector} sector for next quarter."
    pl.log_prompt(prompt)
    return fake_llm(prompt)


@pl.track(model="gpt-4o", temperature=0.2)
def risk_agent(idea: str) -> str:
    prompt = f"Stress test this investment idea under bear market conditions: {idea}"
    pl.log_prompt(prompt)
    return fake_llm(prompt)


@pl.track(model="gpt-4o", temperature=0.3)
def manager_agent(report: str) -> str:
    prompt = f"Make a final portfolio decision based on this risk assessment: {report}"
    pl.log_prompt(prompt)
    result = fake_llm(prompt)
    # Example of programmatic feedback when you know the expected outcome
    pl.log_feedback(score=0.9, label="PASS", notes="Decision looks reasonable")
    return result


if __name__ == "__main__":
    theme = market_agent("semiconductors")
    risk = risk_agent(theme)
    decision = manager_agent(risk)

    print(f"Decision: {decision}")
    print()
    print("All runs logged. Starting interactive review...")
    print("(feedback_mode='end' will launch `promptlog review` automatically)")
