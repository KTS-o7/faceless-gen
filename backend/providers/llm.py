from langchain_openai import ChatOpenAI

from backend.models.config import settings


def get_llm(temperature: float = 0.7) -> ChatOpenAI:
    """Return a ChatOpenAI instance configured to use the Bifrost gateway."""
    return ChatOpenAI(
        model=settings.bifrost_model,
        api_key=settings.bifrost_api_key,
        base_url=settings.bifrost_base_url,
        temperature=temperature,
    )
