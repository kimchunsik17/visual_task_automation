import os
from typing import TypedDict, Annotated, List, Dict, Any
from langgraph.graph import StateGraph, START, END
from langchain_google_genai import ChatGoogleGenerativeAI
from dotenv import load_dotenv

load_dotenv()

# Define the state schema
class GraphState(TypedDict):
    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]
    gemini_response: str

def process_flow(state: GraphState):
    """
    Node function that parses the graph data and calls Gemini API
    """
    nodes = state.get("nodes", [])
    edges = state.get("edges", [])
    
    # Simple prompt describing the graph structure
    prompt = f"Here is a workflow diagram data. Please summarize what this workflow is trying to achieve in a simple, professional tone.\n\nNodes: {nodes}\nEdges: {edges}"
    
    # Check if Gemini API key exists
    if not os.getenv("GEMINI_API_KEY"):
        return {"gemini_response": "Error: GEMINI_API_KEY environment variable is not set."}
    
    try:
        llm = ChatGoogleGenerativeAI(model="gemini-1.5-pro-latest")
        response = llm.invoke(prompt)
        return {"gemini_response": response.content}
    except Exception as e:
        return {"gemini_response": f"Gemini API Error: {str(e)}"}

# Build the LangGraph
workflow = StateGraph(GraphState)

# Add nodes
workflow.add_node("process_flow", process_flow)

# Add edges
workflow.add_edge(START, "process_flow")
workflow.add_edge("process_flow", END)

# Compile graph
app = workflow.compile()

def run_workflow(nodes: list, edges: list) -> str:
    """
    Helper function to run the graph and extract the response
    """
    initial_state = {"nodes": nodes, "edges": edges, "gemini_response": ""}
    result = app.invoke(initial_state)
    return result["gemini_response"]
