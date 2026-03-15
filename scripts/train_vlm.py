"""LoRA fine-tune wrapper that applies transformers patches first."""

import sys
sys.path.insert(0, ".")

from keysay.llm._patches import apply_transformers_patches
apply_transformers_patches()

import runpy
runpy.run_module("mlx_vlm.lora", run_name="__main__")
