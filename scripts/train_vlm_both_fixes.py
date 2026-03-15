"""Train with both Bug 1 (images) and Bug 2 (gate projections) fixes."""

import sys

sys.path.insert(0, ".")

from keysay.llm._patches import apply_transformers_patches

apply_transformers_patches()

# Bug 1: pass images to vision encoder
import scripts.fix_mlxvlm_datasets  # noqa: F401

# Bug 2: exclude DeltaRNN gate projections from LoRA
from mlx_vlm.trainer import utils as trainer_utils
import mlx.nn as nn


def _patched_find_all_linear_names(model):
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

import runpy

runpy.run_module("mlx_vlm.lora", run_name="__main__")
