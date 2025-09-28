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
from langchain.agents import create_react_agent, AgentExecutor
from tool import getProductDetails, getProductLinks
import json

load_dotenv()
google_api_key = os.getenv("google_api_key", "")


class AgentState(TypedDict):
    messages: List[Any]
    user_query: str
    link_results: Dict[str, Any]
    details_results: Dict[str, Any]
    selected_links: List[Dict[str, Any]]
    final_output: Dict[str, Any]
    errors: List[str]
    next: str


def create_agent(llm_name: str, tools: list, prompt: str):
    llm_model = ChatGoogleGenerativeAI(
        model=llm_name,
        google_api_key=google_api_key
    )

    agent = create_react_agent(
        llm=llm_model,
        tools=tools,
        prompt=prompt
    )

    return AgentExecutor(agent=agent, tools=tools, verbose=True)


# Create agents
link_chain_agent = create_agent(
    llm_name="gemini-1.5-flash",
    tools=[getProductLinks],
    prompt=LinkNodePrompt
)

detail_extract_agent = create_agent(
    llm_name="gemini-1.5-flash",
    tools=[getProductDetails],
    prompt=DetailNodePrompt
)


def link_chain_node(state: AgentState) -> Dict[str, Any]:
    """Extract product links based on user query"""
    try:
        user_query = state.get("user_query", "")
        if not user_query:
            # Extract query from messages if not in state
            for msg in state.get("messages", []):
                if isinstance(msg, HumanMessage):
                    user_query = msg.content
                    break

        result = link_chain_agent.invoke({
            "input": f"Search for product links for: {user_query}"
        })

        # Parse the result to extract structured data
        output = result.get("output", "")

        return {
            "link_results": {"raw_output": output, "query": user_query},
            "messages": state["messages"] + [
                AIMessage(content=output, name="link_chain_node")
            ]
        }
    except Exception as e:
        error_msg = f"Error in link_chain_node: {str(e)}"
        return {
            "errors": state.get("errors", []) + [error_msg],
            "messages": state["messages"] + [
                AIMessage(content=error_msg, name="link_chain_node")
            ]
        }


def detail_extract_node(state: AgentState) -> Dict[str, Any]:
    """Extract detailed product information from links"""
    try:
        link_results = state.get("link_results", {})
        selected_links = state.get("selected_links", [])

        # If no selected links, try to extract from link_results
        if not selected_links and link_results:
            # This would need to be parsed from the link_results
            # For now, we'll pass the link_results to the agent
            input_data = json.dumps(link_results)
        else:
            input_data = json.dumps(selected_links)

        result = detail_extract_agent.invoke({
            "input": f"Extract detailed product information from these links: {input_data}"
        })

        output = result.get("output", "")

        return {
            "details_results": {"raw_output": output},
            "messages": state["messages"] + [
                AIMessage(content=output, name="detail_extract_node")
            ]
        }
    except Exception as e:
        error_msg = f"Error in detail_extract_node: {str(e)}"
        return {
            "errors": state.get("errors", []) + [error_msg],
            "messages": state["messages"] + [
                AIMessage(content=error_msg, name="detail_extract_node")
            ]
        }


def supervisor_node(state: AgentState) -> Dict[str, Any]:
    """Supervisor decides which node to execute next"""
    try:
        supervisor_model = ChatGoogleGenerativeAI(
            model="gemini-1.5-flash",
            google_api_key=google_api_key
        )

        # Get the current state and decide next action
        messages = state.get("messages", [])
        user_query = state.get("user_query", "")
        link_results = state.get("link_results", {})
        details_results = state.get("details_results", {})

        # Build context for supervisor
        context = f"""
        User Query: {user_query}
        Link Results Available: {'Yes' if link_results else 'No'}
        Details Results Available: {'Yes' if details_results else 'No'}
        
        Recent Messages:
        {json.dumps([msg.content if hasattr(msg, 'content') else str(msg) for msg in messages[-3:]], indent=2)}
        """

        supervisor_prompt = f"""
        {SupervisorNodePrompt}
        
        Current Context: {context}
        
        Based on the current state, decide the next action:
        - If no links have been extracted yet, choose 'link_chain_node'
        - If links are available but no details extracted, choose 'detail_extract_node'  
        - If both links and details are available, choose 'FINISH'
        
        Respond with just the node name: link_chain_node, detail_extract_node, or FINISH
        """

        response = supervisor_model.invoke([HumanMessage(content=supervisor_prompt)])
        next_node = response.content.strip()

        # Validate the response
        if next_node not in ["link_chain_node", "detail_extract_node", "FINISH"]:
            # Default logic based on state
            if not link_results:
                next_node = "link_chain_node"
            elif not details_results:
                next_node = "detail_extract_node"
            else:
                next_node = "FINISH"

        return {
            "next": next_node,
            "messages": state["messages"] + [
                AIMessage(content=f"Supervisor decision: {next_node}", name="supervisor")
            ]
        }

    except Exception as e:
        error_msg = f"Error in supervisor_node: {str(e)}"
        return {
            "next": "FINISH",
            "errors": state.get("errors", []) + [error_msg],
            "messages": state["messages"] + [
                AIMessage(content=error_msg, name="supervisor")
            ]
        }


def should_continue(state: AgentState) -> str:
    """Determine if workflow should continue or end"""
    next_action = state.get("next", "FINISH")
    if next_action == "FINISH":
        return END
    return next_action


def create_workflow():
    """Create the LangGraph workflow"""
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("link_chain_node", link_chain_node)
    workflow.add_node("detail_extract_node", detail_extract_node)

    # Add edges
    workflow.add_edge(START, "supervisor")
    workflow.add_conditional_edges(
        "supervisor",
        should_continue,
        {
            "link_chain_node": "link_chain_node",
            "detail_extract_node": "detail_extract_node",
            END: END
        }
    )
    workflow.add_edge("link_chain_node", "supervisor")
    workflow.add_edge("detail_extract_node", "supervisor")

    # Compile with checkpointer
    checkpointer = MemorySaver()
    app = workflow.compile(checkpointer=checkpointer)

    return app


def run_scraping_agent(user_query: str) -> Dict[str, Any]:
    """Run the complete scraping workflow"""
    app = create_workflow()

    initial_state = {
        "messages": [HumanMessage(content=user_query)],
        "user_query": user_query,
        "link_results": {},
        "details_results": {},
        "selected_links": [],
        "final_output": {},
        "errors": [],
        "next": ""
    }

    config = {"configurable": {"thread_id": "scraping_session"}}

    try:
        final_state = None
        for state in app.stream(initial_state, config=config):
            print(f"Current state keys: {list(state.keys())}")
            final_state = state

        # Extract final results
        if final_state:
            last_state = list(final_state.values())[-1]
            return {
                "success": True,
                "link_results": last_state.get("link_results", {}),
                "details_results": last_state.get("details_results", {}),
                "messages": last_state.get("messages", []),
                "errors": last_state.get("errors", [])
            }
        else:
            return {"success": False, "error": "No final state received"}

    except Exception as e:
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    # Test the workflow
    query = "iPhone 15 Pro Max 256GB"
    print(f"Starting scraping for: {query}")

    result = run_scraping_agent(query)

    if result["success"]:
        print("\n=== SCRAPING RESULTS ===")
        print(f"Link Results: {result['link_results']}")
        print(f"Details Results: {result['details_results']}")
        if result["errors"]:
            print(f"Errors: {result['errors']}")
    else:
        print(f"Scraping failed: {result['error']}")
