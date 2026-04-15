from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    # Bifrost LLM Gateway
    bifrost_base_url: str = Field(default="https://opencode.ai/zen/go/v1")
    bifrost_api_key: str = Field(default="placeholder")
    bifrost_model: str = Field(default="gpt-4o-mini")

    # ElevenLabs TTS
    elevenlabs_api_key: str = Field(default="placeholder")
    elevenlabs_voice_id: str = Field(default="21m00Tcm4TlvDq8ikWAM")

    # Video backend
    video_backend: str = Field(default="local")
    cloud_video_api_key: str = Field(default="")
    cloud_video_base_url: str = Field(default="")

    # Wan I2V model
    wan_model_path: str = Field(default="./models/wan2.2-i2v-5b")

    # Directories
    outputs_dir: Path = Field(default=Path("./outputs"))
    models_dir: Path = Field(default=Path("./models"))

    # FastAPI server
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000)

    # ComfyUI
    comfyui_base_url: str = Field(default="http://127.0.0.1:8188")

    # Personas
    personas_dir: Path = Field(default=Path("backend/assets/personas"))
    active_persona: str = Field(default="default")


settings = Settings()
