"""
PromptLog + LangChain (LCEL, two-agent pipeline)

Agent 1 generates a topic summary.
Agent 2 critiques it.
Each step is tracked as a separate run.

    uv pip install langchain-core langchain-openai python-dotenv
    python examples/test_langchain.py
    promptlog runs --project langchain
"""
from dotenv import load_dotenv

load_dotenv()

import promptlog as pl
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI

pl.init(project="langchain", feedback_mode="end")

MODEL = "gpt-4o-mini"
SUMMARIZE_TEMPERATURE = 0.3
CRITIQUE_TEMPERATURE = 0.7

summarize_model = ChatOpenAI(model=MODEL, temperature=SUMMARIZE_TEMPERATURE)
critique_model = ChatOpenAI(model=MODEL, temperature=CRITIQUE_TEMPERATURE)

summarize_template = PromptTemplate.from_template(
    "In two sentences, explain what {topic} is."
)
critique_template = PromptTemplate.from_template(
    "Critique this explanation in one sentence: {explanation}"
)

summarize_chain = summarize_template | summarize_model | StrOutputParser()
critique_chain = critique_template | critique_model | StrOutputParser()


@pl.track()
def run_pipeline(topic: str) -> dict:
    # Inner agents defined on the fly
    @pl.track(model=MODEL, temperature=SUMMARIZE_TEMPERATURE)
    def summarize(topic: str):
        pl.log_prompt(summarize_template.format(topic=topic))
        return summarize_chain.invoke({"topic": topic})

    @pl.track(model=MODEL, temperature=CRITIQUE_TEMPERATURE)
    def critique(explanation: str):
        pl.log_prompt(critique_template.format(explanation=explanation))
        return critique_chain.invoke({"explanation": explanation})

    # Execution
    summary = summarize(topic)
    comment = critique(summary)
    
    return {"summary": summary, "critique": comment}



if __name__ == "__main__":
    topic = "the French Revolution"
    result = run_pipeline(topic)
    print(result)
    print()
