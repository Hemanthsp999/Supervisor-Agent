# main.py
import os
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from prompts import LinkNodePrompt, DetailNodePrompt, SupervisorNodePrompt
from typing_extensions import TypedDict, Annotated
from typing import Literal, List, Dict, Any
from langgraph.types import Command
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import PromptTemplate
from langchain.agents import create_react_agent
from langgraph_supervisor import create_supervisor
from tool import getProductDetails, getProductLinks  # your @tool functions

load_dotenv()
google_api_key = os.getenv("google_api_key", "")


class AgentState(TypedDict):
    user_query: str
    link_results: Dict[str, Any]
    details_results: Dict[str, Any]
    selected_links: List[Dict[str, Any]]
    final_output: Dict[str, Any]
    errors: List[str]


def create_agent(llm: str, tools: list, prompt: str):

    llm_model = ChatGoogleGenerativeAI(
        model=llm,
        google_api_key=google_api_key
    )

    agent = create_react_agent(
        llm=llm_model,
        tools=tools,
        prompt=prompt
    )

    return agent


link_chain_agent = create_agent(
    llm="gemini-2.5",
    tools=[getProductLinks],
    prompt=LinkNodePrompt
)

detail_extract_agent = create_agent(
    llm="gemini-2.0",
    tools=[getProductDetails],
    prompt=DetailNodePrompt
)


def link_chain_node(state: AgentState) -> AgentState:
    result = link_chain_agent.invoke(state)
    return Command(
        update={
            "messages": state["messages"] + [
                AIMessage(content=result["messages"][-1].content, name="link_chain_node")
            ]
        },
        goto="supervisor"
    )


def detail_extract_node(state: AgentState) -> AgentState:
    result = detail_extract_agent.invoke(state)
    return Command(
        update={
            "messages": state["messages"] + [
                AIMessage(content=result["messages"][-1].content, name="detail_extract_node")
            ]
        },
        goto="supervisor"
    )


supervisor_model = ChatGoogleGenerativeAI()

agent_tools = {'link_chain_node': 'You are an expert scrapper for the given query. Return the scraped result in structured way',
               'detail_extract_node': 'You are an expert Product detail extractor. based on the given list[dict[str]] extract the details of the product. Return it in strutured way.'}
options = list(agent_tools.keys()) + ["FINISH"]
worker_info = '\n\n'.join([f'WORKER: {member} \nDESCRIPTION: {description}' for member, description in agent_tools.items(
)]) + '\n\nWORKER: FINISH \nDESCRIPTION: If User Query is answered and route to Finished'


class Router(TypedDict):
    """
    Worker to route to next. If no workers needed, route to FINISH. and provide reasoning for the routing
    """
    next: Annotated[Literal[options], ..., "worker route to next, route to FINISH"]
    reasoning: Annotated[str, ..., "support proper reason for routing to the worker"]


supervisor_agent = create_supervisor(
    [link_chain_agent, detail_extract_agent],
    model=supervisor_model,
    prompt=SupervisorNodePrompt
)


def supervisorNode(state: AgentState) -> Command[Literal[list(agent_tools.keys()), "__end__"]]:
    return supervisor_agent.compile(checkpointer=MemorySaver)


if __name__ == "__main__":
    resu = supervisorNode()

    for r in resu:
        print(f"Result: {r.content}")
