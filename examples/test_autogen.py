"""
PromptLog + AutoGen (three-agent conversation)

A writer drafts an answer, a critic reviews it, and a user_proxy drives the flow.
The full conversation is captured as a single tracked run.

    uv pip install "pyautogen" "autogen-ext[openai]" python-dotenv
    python examples/test_autogen.py
    promptlog runs --project autogen
"""
import asyncio

from dotenv import load_dotenv

load_dotenv()

import promptlog as pl
from autogen_agentchat.agents import AssistantAgent, UserProxyAgent
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_agentchat.conditions import MaxMessageTermination
from autogen_ext.models.openai import OpenAIChatCompletionClient

pl.init(project="autogen", feedback_mode="end")

MODEL = "gpt-4o-mini"
TEMPERATURE = 0.5

model_client = OpenAIChatCompletionClient(model=MODEL, temperature=TEMPERATURE)

writer = AssistantAgent(
    name="writer",
    model_client=model_client,
    system_message="You are a writer. Answer the question clearly in one sentence.",
)

critic = AssistantAgent(
    name="critic",
    model_client=model_client,
    system_message="You are a critic. Review the writer's answer and suggest one improvement.",
)

user_proxy = UserProxyAgent(name="user_proxy")

TASK = "What is the capital of France and why is it significant?"


@pl.track(model=MODEL, temperature=TEMPERATURE)
def run_conversation(task: str) -> str:
    pl.log_prompt(task)

    async def _run() -> str:
        team = RoundRobinGroupChat(
            [writer, critic, user_proxy],
            termination_condition=MaxMessageTermination(max_messages=4),
        )
        result = await team.run(task=task)
        # Return the last assistant message
        for msg in reversed(result.messages):
            if msg.source in ("writer", "critic"):
                return msg.content
        return ""

    return asyncio.run(_run())


if __name__ == "__main__":
    result = run_conversation(TASK)
    print(f"\n[final] {result}\n")
    print()
