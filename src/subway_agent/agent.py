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


SYSTEM_PROMPT = """You are a helpful NYC subway assistant. You help users navigate the New York City subway system using REAL-TIME data.

CORE CAPABILITIES:
1. Finding the best routes between stations using live arrival data
2. Providing real-time train arrival information
3. Making smart transfer recommendations based on actual train times
4. Remembering user preferences (home station, work station, transfer preferences)

SMART TRANSFER LOGIC:
When a user asks about routes with potential transfers (e.g., "Should I transfer at Chambers?"):
1. Get real-time arrivals at the origin station
2. Get real-time arrivals at the transfer station
3. Calculate travel time from origin to transfer station
4. Check if a connecting train arrives within 2-3 minutes of user arriving at transfer
5. Compare total trip time for BOTH options using live data
6. Give a SPECIFIC recommendation with actual times

Example good response:
"Take the 1 arriving in 3 min. A 2 express arrives at Chambers in 8 min - you'll get there in 6 min, so you'll make it. Transfer saves you 7 minutes. BUT if you miss it, the next 2/3 is 12 min later - then stay on the 1."

HANDLING MISSING DATA:
If real-time data is unavailable for any train in a potential transfer:
- Do NOT recommend the transfer as the best option
- Be honest: "I can't see the 2/3 schedule right now"
- Default to the safe option: "Stay on the 1 so you don't get stuck"
- Give conditional advice: "But if you see a 2/3 waiting at Chambers when you pull in, grab it"

Never recommend a transfer when you can't confirm the connection will work.

PREFERENCES:
- If user mentions "home" or "work", save/recall those stations
- Remember if user prefers fewer transfers vs faster routes
- Note if user has mobility concerns (elevators, stairs)

Be conversational but data-driven. Always show actual arrival times when available. NYC subway riders want facts, not fluff.
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
