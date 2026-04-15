#!/usr/bin/env python3
"""Verify PyTorch MPS (Metal Performance Shaders) is available on Apple Silicon."""
import sys

try:
    import torch
except ImportError:
    print("ERROR: torch not installed. Run: pip install torch torchvision torchaudio")
    sys.exit(1)

available = torch.backends.mps.is_available()
print(f"MPS available: {available}")

if not available:
    print("ERROR: MPS not available. Are you on Apple Silicon with PyTorch >= 2.0?")
    sys.exit(1)

# Verify MPS compute actually works
device = torch.device("mps")
a = torch.randn(100, 100, device=device)
b = torch.randn(100, 100, device=device)
c = torch.matmul(a, b)
print(f"device: {device}")
print(f"Test matmul shape: {c.shape}")
print("MPS compute OK")
