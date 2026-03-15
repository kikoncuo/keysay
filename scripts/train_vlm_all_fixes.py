"""Train with all 3 fixes: images, gate exclusion, and alpha/rank scaling."""

import sys

sys.path.insert(0, ".")

from keysay.llm._patches import apply_transformers_patches

apply_transformers_patches()

# Bug 1: pass images to vision encoder
import scripts.fix_mlxvlm_datasets  # noqa: F401

# Bug 2: exclude DeltaRNN gate projections
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

# Bug 3: fix alpha scaling (alpha/rank instead of raw alpha)
import math
from mlx_vlm.trainer.lora import LoRaLayer
import mlx.core as mx

_orig_init = LoRaLayer.__init__


def _patched_init(self, linear, rank, alpha=0.1, dropout=0.0):
    _orig_init(self, linear, rank, alpha, dropout)
    # Override: use alpha/rank scaling (standard LoRA convention)
    self.scale = alpha / rank
    # Remove the old raw alpha attribute
    if hasattr(self, "alpha"):
        delattr(self, "alpha")


def _patched_call(self, x):
    y = self.original_layer(x)
    lora_update = (self.dropout(x) @ self.A) @ self.B
    return y + (self.scale * lora_update).astype(x.dtype)


LoRaLayer.__init__ = _patched_init
LoRaLayer.__call__ = _patched_call

# Bug 4: dataset.select(range(iters)) crashes when iters > dataset size.
# Fix: patch HF Dataset.select to wrap indices with modulo.
from datasets import Dataset

_orig_select = Dataset.select


def _repeating_select(self, indices, *args, **kwargs):
    if hasattr(indices, '__len__') and len(indices) > 0:
        max_idx = max(indices) if not isinstance(indices, range) else indices[-1]
        if max_idx >= len(self):
            indices = [i % len(self) for i in indices]
    elif isinstance(indices, range) and indices[-1] >= len(self):
        indices = [i % len(self) for i in indices]
    return _orig_select(self, indices, *args, **kwargs)


Dataset.select = _repeating_select

import runpy

runpy.run_module("mlx_vlm.lora", run_name="__main__")
