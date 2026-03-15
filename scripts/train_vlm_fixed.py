"""LoRA fine-tune wrapper with Bug 1 fix + transformers patches.

Quick test: 10 iters to validate images are being trained on.
"""

import sys
sys.path.insert(0, ".")

# Apply transformers patches (video processor crash fix)
from keysay.llm._patches import apply_transformers_patches
apply_transformers_patches()

# Apply Bug 1 fix (images discarded for Qwen models)
import scripts.fix_mlxvlm_datasets  # noqa: F401

import runpy
runpy.run_module("mlx_vlm.lora", run_name="__main__")
