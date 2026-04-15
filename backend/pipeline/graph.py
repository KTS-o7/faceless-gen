from langgraph.graph import END, START, StateGraph

from backend.pipeline.nodes.assembly import assembly_node
from backend.pipeline.nodes.audio import audio_node
from backend.pipeline.nodes.image_gen import image_gen_node
from backend.pipeline.nodes.scripting import scripting_node
from backend.pipeline.nodes.video import video_node
from backend.pipeline.state import PipelineState


def build_graph():
    """Build and compile the sequential LangGraph pipeline."""
    graph = StateGraph(PipelineState)

    # Register nodes
    graph.add_node("scripting", scripting_node)
    graph.add_node("audio", audio_node)
    graph.add_node("image_gen", image_gen_node)
    graph.add_node("video", video_node)
    graph.add_node("assembly", assembly_node)

    # Sequential edges: START → scripting → audio → image_gen → video → assembly → END
    graph.add_edge(START, "scripting")
    graph.add_edge("scripting", "audio")
    graph.add_edge("audio", "image_gen")
    graph.add_edge("image_gen", "video")
    graph.add_edge("video", "assembly")
    graph.add_edge("assembly", END)

    return graph.compile()


compiled_graph = build_graph()
