import os
from dotenv import load_dotenv
from typing_extensions import TypedDict, Annotated
from typing import Literal
from langgraph.types import Command
from langgraph.graph import StateGraph, START
from langgraph.checkpoint.memory import MemorySaver
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import PromptTemplate
from langchain.agents import create_react_agent
from tool import getProductDetails, getProductLinks

load_dotenv()
google_api_key = os.getenv("google_api_key")


class AgentState(TypedDict):
    user_query: str


class Route(TypedDict):
    """Worker to route to next. If no workers needed, route to FINISH. and provide reasoning for the routing"""

    next: Annotated[Literal[*options], ..., "worker to route to next, route to FINISH"]
    reasoning: Annotated[str, ..., "Support proper reasoning for routing to the worker"]


def create_agent(llm: str, tools: list, prompt: list[str]):
    getModel = ChatGoogleGenerativeAI(
        model=llm,
        google_api_key=google_api_key,
        temperature=0.7
    )

    getPrompt = PromptTemplate.from_template(
        prompt
    )

    agent = create_react_agent(
        model=getModel,
        tools=tools,
        prompt=getPrompt
    )

    return agent


link_extractor_agent = create_agent(
    llm="",
    tools=[getProductLinks],
    prompt=""
)

product_detail_extractor_agent = create_agent(
    llm="",
    tools=[getProductDetails],
    prompt=""
)


def productLinkNode(state: AgentState):
    invokeAgent = link_extractor_agent.invoke(state)

    return Command(
        update={
        },
        goto="supervisor"
    )


def productDetailsNode(state: AgentState):
    invokeProductAgent = product_detail_extractor_agent.invoke(state)

    return Command(
        update={
        },
        goto="supervisor"
    )


member_tools = {'productLinkNode': '', 'productDetailsNode': ''}
options = list(member_tools.keys()) + ["FINISH"]
worker_info = '\n\n'.join([f'WORKER: {member_tools} \nDESCRIPTION: {description}' for member, description in members_tools.items(
)]) + '\n\nWORKER: FINISH \nDESCRIPTION: If User Query is answered and route to Finished'


def supervisor_node(state: AgentState) -> Command[Literal[*list(members_dict.keys()), "__end__"]]:
    return Command(goto=goto, update={"next": goto, 'cur_reasoning': response["reasoning"]})


def init_graph(state: AgentState):
    build = StateGraph(AgentState)

    build.add_edge(START, "supervisor")

    build.add_node("supervisor", supervisor_node)
    build.add_node("link_node", productLinkNode)
    build.add_node("details_node", productDetailsNode)

    build.add_conditional_edges(link_node, supervisor)
    build.add_conditional_edges(details_node, supervisor)

    return build


if __name__ == "__main__":

    build_graph = init_graph()
    build_graph.compile(checkpointer=MemorySaver())
