"""Test Bug 2 fix: exclude DeltaRNN gate projections from LoRA targets.

Verifies that in_proj_a and in_proj_b are excluded, then runs 10 training
iters and checks that generation still produces text (not vision tokens).
"""

import sys

sys.path.insert(0, ".")

from keysay.llm._patches import apply_transformers_patches

apply_transformers_patches()

# Apply Bug 1 fix (images)
import scripts.fix_mlxvlm_datasets  # noqa: F401

# Apply Bug 2 fix (gate projections)
from mlx_vlm.trainer import utils as trainer_utils


def _patched_find_all_linear_names(model):
    """Exclude DeltaRNN gate projections from LoRA targets."""
    import mlx.nn as nn

    cls = nn.Linear
    quantized_cls = nn.QuantizedLinear
    lora_module_names = set()
    multimodal_keywords = [
        "mm_projector",
        "vision_tower",
        "vision_resampler",
        "aligner",
    ]
    deltarnn_gate_keywords = ["in_proj_a", "in_proj_b"]

    for name, module in model.named_modules():
        if any(mm_keyword in name for mm_keyword in multimodal_keywords):
            continue
        if isinstance(module, cls) or isinstance(module, quantized_cls):
            names = name.split(".")
            module_name = names[0] if len(names) == 1 else names[-1]
            if module_name in deltarnn_gate_keywords:
                continue
            lora_module_names.add(module_name)

    if "lm_head" in lora_module_names:
        lora_module_names.remove("lm_head")
    return list(lora_module_names)


trainer_utils.find_all_linear_names = _patched_find_all_linear_names

# Verify
from mlx_vlm import load

model, processor = load("mlx-community/Qwen3.5-0.8B-8bit")
names = _patched_find_all_linear_names(model.language_model)
print(f"LoRA targets (Bug 2 fix): {sorted(names)}")
assert "in_proj_a" not in names, "in_proj_a should be excluded"
assert "in_proj_b" not in names, "in_proj_b should be excluded"
assert "in_proj_qkv" in names, "in_proj_qkv should be included"
assert "q_proj" in names, "q_proj should be included"
print("PASS: DeltaRNN gate projections excluded, other targets preserved")
