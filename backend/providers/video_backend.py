import abc
import logging
from pathlib import Path
from typing import Optional

from backend.models.config import settings
from backend.pipeline.editorial import STYLE_CONSTRAINTS

logger = logging.getLogger(__name__)


class VideoBackend(abc.ABC):
    """Abstract base class for video generation backends."""

    @abc.abstractmethod
    def generate_clip(
        self,
        prompt: str,
        first_frame_image_path: str,
        output_path: str,
        duration_seconds: int = 5,
    ) -> str:
        """
        Generate a video clip from a first-frame image and a prompt.

        Args:
            prompt: Text prompt describing the clip's motion.
            first_frame_image_path: Path to the anchor image (first frame).
            output_path: Destination path for the output MP4.
            duration_seconds: Desired clip length in seconds.

        Returns:
            Absolute path to the saved MP4.
        """
        ...


class LocalWanBackend(VideoBackend):
    """I2V backend using diffusers WanImageToVideoPipeline on MPS."""

    _pipeline = None  # Class-level lazy-loaded pipeline cache

    @classmethod
    def _get_pipeline(cls):
        if cls._pipeline is None:
            import torch
            from diffusers import WanImageToVideoPipeline

            logger.info("Loading WanImageToVideoPipeline from %s", settings.wan_model_path)
            pipe = WanImageToVideoPipeline.from_pretrained(
                settings.wan_model_path,
                torch_dtype=torch.float16,
            )
            pipe.enable_model_cpu_offload()
            cls._pipeline = pipe
        return cls._pipeline

    def generate_clip(
        self,
        prompt: str,
        first_frame_image_path: str,
        output_path: str,
        duration_seconds: int = 5,
    ) -> str:
        import imageio
        from PIL import Image

        full_prompt = f"{prompt}, {STYLE_CONSTRAINTS}"
        pipe = self._get_pipeline()

        image = Image.open(first_frame_image_path).convert("RGB")

        result = pipe(
            image=image,
            prompt=full_prompt,
            num_frames=duration_seconds * 8,  # ~8 fps
        )
        frames = result.frames[0]  # list of PIL Images

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        writer = imageio.get_writer(output_path, fps=8, format="ffmpeg", codec="libx264")
        try:
            import numpy as np
            for frame in frames:
                writer.append_data(np.array(frame))
        finally:
            writer.close()

        return str(Path(output_path).resolve())


class CloudVideoBackend(VideoBackend):
    """Stub cloud video backend — not yet implemented."""

    def generate_clip(
        self,
        prompt: str,
        first_frame_image_path: str,
        output_path: str,
        duration_seconds: int = 5,
    ) -> str:
        raise NotImplementedError(
            "CloudVideoBackend is not yet implemented. "
            "Set VIDEO_BACKEND=local to use the local Wan I2V backend."
        )


def get_video_backend() -> VideoBackend:
    """Factory — returns the configured video backend."""
    if settings.video_backend == "cloud":
        return CloudVideoBackend()
    return LocalWanBackend()
