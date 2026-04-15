from langgraph.graph import END, START, StateGraph

from backend.pipeline.nodes.assembly import assembly_node
from backend.pipeline.nodes.audio import audio_node
from backend.pipeline.nodes.image_gen import image_gen_node
from backend.pipeline.nodes.persona import load_persona_node
from backend.pipeline.nodes.scripting import scripting_node
from backend.pipeline.nodes.video import video_node
from backend.pipeline.state import PipelineState


def _route_start(state: PipelineState) -> str:
    """If scenes are pre-populated (project mode), skip scripting and load persona first."""
    if state.get("scenes") and len(state["scenes"]) > 0:
        return "load_persona"
    return "scripting"


def build_graph():
    """Build and compile the sequential LangGraph pipeline."""
    graph = StateGraph(PipelineState)

    # Register nodes
    graph.add_node("scripting", scripting_node)
    graph.add_node("load_persona", load_persona_node)
    graph.add_node("audio", audio_node)
    graph.add_node("image_gen", image_gen_node)
    graph.add_node("video", video_node)
    graph.add_node("assembly", assembly_node)

    # Conditional start: project mode vs prompt mode
    graph.add_conditional_edges(
        START,
        _route_start,
        {
            "scripting": "scripting",
            "load_persona": "load_persona",
        },
    )

    graph.add_edge("scripting", "audio")
    graph.add_edge("load_persona", "audio")
    graph.add_edge("audio", "image_gen")
    graph.add_edge("image_gen", "video")
    graph.add_edge("video", "assembly")
    graph.add_edge("assembly", END)

    return graph.compile()


compiled_graph = build_graph()
