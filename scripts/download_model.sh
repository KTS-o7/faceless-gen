#!/bin/bash
# Download Wan 2.2 I2V 5B model in diffusers format
# NOTE: This is ~20GB. Only run when ready to test video generation.
set -e

MODEL_DIR="./models/wan2.2-i2v-5b"
mkdir -p "$MODEL_DIR"

echo "Downloading Wan 2.2 I2V 5B from HuggingFace..."
echo "Note: This is approximately 20GB and will take a while."
echo ""

huggingface-cli download Wan-AI/Wan2.2-I2V-5B-480P \
  --local-dir "$MODEL_DIR" \
  --local-dir-use-symlinks False

echo ""
echo "Download complete!"
echo "Set in .env:"
echo "  WAN_MODEL_PATH=$(pwd)/$MODEL_DIR"
