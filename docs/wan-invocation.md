# Wan 2.2 I2V Inference via diffusers + MPS

## Model
- HuggingFace repo: `Wan-AI/Wan2.2-I2V-5B-480P`
- Local path: `./models/wan2.2-i2v-5b` (after running `scripts/download_model.sh`)

## Python API

```python
import torch
from diffusers import WanImageToVideoPipeline
from PIL import Image

pipe = WanImageToVideoPipeline.from_pretrained(
    "./models/wan2.2-i2v-5b",
    torch_dtype=torch.float16,
)
pipe.enable_model_cpu_offload()  # Required on 18GB unified RAM

image = Image.open("scene_00.png").convert("RGB").resize((832, 480))

output = pipe(
    image=image,
    prompt="stickman figure walking forward, flat 2D animation",
    negative_prompt="realistic, 3D, shadows, gradients",
    num_frames=49,        # ~4 seconds at 12fps
    num_inference_steps=20,
    guidance_scale=5.0,
)

frames = output.frames[0]
# Export frames to MP4 using imageio
import imageio
writer = imageio.get_writer("output.mp4", fps=12)
for frame in frames:
    writer.append_data(frame)
writer.close()
```

## Notes
- `enable_model_cpu_offload()` is required to fit within 18GB unified RAM
- Resolution: 832x480 (16:9 landscape) or 480x832 (9:16 portrait)
- 49 frames at 12fps = ~4 seconds per clip
- Inference time: ~10-15 minutes per clip on M3 Pro (MPS)
- Do NOT use `.to("mps")` directly — use `enable_model_cpu_offload()` instead for memory safety
