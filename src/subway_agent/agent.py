"""LangGraph agent for NYC subway routing."""

from __future__ import annotations

import json
import re
from typing import Annotated, TypedDict, Optional

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, BaseMessage, ToolMessage
from langchain_groq import ChatGroq
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from .config import GROQ_API_KEY, GROQ_MODEL
from .tools import ALL_TOOLS, get_route, get_train_arrivals, get_station_info, find_stations_on_line, save_preference, get_preference, get_common_trips
from .database import db


# Agent state
class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    user_id: str


# Tool name to function mapping
TOOL_MAP = {
    "get_route": get_route,
    "get_train_arrivals": get_train_arrivals,
    "get_station_info": get_station_info,
    "find_stations_on_line": find_stations_on_line,
    "save_preference": save_preference,
    "get_preference": get_preference,
    "get_common_trips": get_common_trips,
}


SYSTEM_PROMPT = """You are a helpful NYC subway assistant. You help users navigate the New York City subway system by:

1. Finding the best routes between stations
2. Providing real-time train arrival information
3. Answering questions about stations and lines
4. Remembering user preferences (home station, work station, etc.)

When users ask about routes, always use the get_route tool to find the best path.
When they want to know when trains are coming, use get_train_arrivals.
If they mention "home" or "work", check if you have saved preferences for those locations.

Be conversational and helpful. If a station name is ambiguous, ask for clarification.
You can remember things for users - for example, if they say "my home station is Times Square",
save that preference so you can use it later.

Keep responses concise but informative. NYC subway riders are busy people!
"""


def parse_legacy_tool_call(text: str) -> Optional[tuple[str, dict]]:
    """Parse legacy XML-style tool calls that some models produce.

    Handles formats like:
    - <function=tool_name{"arg": "value"}</function>
    - <function=tool_name>{"arg": "value"}</function>
    """
    patterns = [
        r'<function=(\w+)\{(.+?)\}</function>',
        r'<function=(\w+)>\{(.+?)\}</function>',
        r'<function=(\w+)>(.+?)</function>',
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            tool_name = match.group(1)
            try:
                # Try to parse the args as JSON
                args_str = match.group(2)
                if not args_str.startswith('{'):
                    args_str = '{' + args_str + '}'
                args = json.loads(args_str)
                return tool_name, args
            except json.JSONDecodeError:
                continue

    return None


def execute_tool(tool_name: str, args: dict) -> str:
    """Execute a tool by name with given arguments."""
    if tool_name in TOOL_MAP:
        tool_func = TOOL_MAP[tool_name]
        try:
            return tool_func.invoke(args)
        except Exception as e:
            return f"Error executing {tool_name}: {str(e)}"
    return f"Unknown tool: {tool_name}"


def create_agent():
    """Create the LangGraph subway agent."""
    # Initialize LLM with explicit tool choice
    llm = ChatGroq(
        api_key=GROQ_API_KEY,
        model=GROQ_MODEL,
        temperature=0.1,
    )

    # Bind tools with explicit configuration
    llm_with_tools = llm.bind_tools(
        ALL_TOOLS,
        tool_choice="auto",
    )

    def call_model(state: AgentState) -> dict:
        """Call the LLM with the current state."""
        messages = state["messages"]

        # Add system message if not present
        if not messages or not isinstance(messages[0], SystemMessage):
            messages = [SystemMessage(content=SYSTEM_PROMPT)] + list(messages)

        try:
            response = llm_with_tools.invoke(messages)

            # Check if the response contains legacy tool call format
            if hasattr(response, 'content') and response.content:
                legacy_call = parse_legacy_tool_call(response.content)
                if legacy_call and (not hasattr(response, 'tool_calls') or not response.tool_calls):
                    tool_name, tool_args = legacy_call
                    # Execute the tool directly and create a new response
                    tool_result = execute_tool(tool_name, tool_args)

                    # Return a clean AI message with the tool result incorporated
                    clean_response = AIMessage(content=f"{tool_result}")
                    return {"messages": [clean_response]}

            return {"messages": [response]}

        except Exception as e:
            error_msg = str(e)

            # Check if this is a tool calling format error
            if "tool_use_failed" in error_msg or "failed_generation" in error_msg:
                # Try to extract the legacy tool call from the error
                legacy_match = re.search(r"'failed_generation':\s*'(.+?)'", error_msg, re.DOTALL)
                if legacy_match:
                    failed_gen = legacy_match.group(1)
                    legacy_call = parse_legacy_tool_call(failed_gen)
                    if legacy_call:
                        tool_name, tool_args = legacy_call
                        tool_result = execute_tool(tool_name, tool_args)
                        return {"messages": [AIMessage(content=tool_result)]}

            # Return error as a message
            return {"messages": [AIMessage(content=f"I encountered an error: {error_msg}")]}

    def should_continue(state: AgentState) -> str:
        """Determine if we should continue to tools or end."""
        last_message = state["messages"][-1]

        # If there are tool calls, route to tools
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools"

        return END

    # Create tool node
    tool_node = ToolNode(ALL_TOOLS)

    # Build graph
    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node("agent", call_model)
    graph.add_node("tools", tool_node)

    # Add edges
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")

    return graph.compile()


# Compiled agent - created lazily to avoid import-time errors
_agent = None

def get_agent():
    """Get or create the agent instance."""
    global _agent
    if _agent is None:
        _agent = create_agent()
    return _agent


def chat(message: str, user_id: str = "default") -> str:
    """Send a message to the agent and get a response.

    Args:
        message: The user's message
        user_id: User identifier for personalization

    Returns:
        The agent's response
    """
    # Save user message to history
    db.add_message("user", message, user_id)

    # Get conversation context
    history = db.get_recent_messages(user_id, limit=6)
    messages = []

    for msg in history[:-1]:  # Exclude current message (already in history)
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        else:
            messages.append(AIMessage(content=msg["content"]))

    # Add current message
    messages.append(HumanMessage(content=message))

    # Run agent
    agent = get_agent()
    result = agent.invoke({
        "messages": messages,
        "user_id": user_id
    })

    # Extract response
    response = result["messages"][-1].content

    # Save assistant response to history
    db.add_message("assistant", response, user_id)

    return response


def clear_history(user_id: str = "default"):
    """Clear conversation history for a user."""
    db.clear_conversation(user_id)
