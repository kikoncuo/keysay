"""Test that VisionDataset.process correctly passes images for Qwen3.5.

Validates Bug 1 fix: before the patch, pixel_values is None for Qwen models.
After the patch, pixel_values should contain actual image features.
"""

import sys
sys.path.insert(0, ".")

from keysay.llm._patches import apply_transformers_patches
apply_transformers_patches()

from mlx_vlm import load
from mlx_vlm.lora import transform_dataset_to_messages
from mlx_vlm.trainer.datasets import VisionDataset
from datasets import load_dataset


def load_model_and_data():
    """Load model and prepare dataset (shared by both tests)."""
    model, processor = load("mlx-community/Qwen3.5-0.8B-8bit")

    # Build config dict from model
    config = {}
    c = model.config
    for key in ["model_type", "image_token_index", "image_token_id"]:
        val = getattr(c, key, None)
        if val is None and isinstance(c, dict):
            val = c.get(key)
        if val is not None:
            config[key] = val
    if not config.get("image_token_index") and not config.get("image_token_id"):
        config["image_token_index"] = 248056

    # Load and transform dataset (adds messages column)
    ds = load_dataset("Enriqueag26/keysay-vlm-context-training", split="train")
    ds = ds.select(range(1))
    ds = transform_dataset_to_messages(ds, config.get("model_type", "qwen3_5"), None)

    return model, processor, config, ds


def test_unpatched(model, processor, config, ds):
    """Show the bug: original VisionDataset discards images."""
    print("=" * 60)
    print("TEST 1: Unpatched (original mlx-vlm behavior)")
    print("=" * 60)

    dataset = VisionDataset(ds, config, processor)
    item = dataset[0]

    pv = item.get("pixel_values")
    ids = item.get("input_ids")

    has_bug = pv is None
    print(f"  pixel_values: {'NONE (BUG!)' if has_bug else f'shape {pv.shape}'}")
    print(f"  input_ids tokens: {ids.shape[-1]}")

    if has_bug:
        print(f"  CONFIRMED: images discarded — only {ids.shape[-1]} tokens (no image expansion)")
    return has_bug


def test_patched(model, processor, config, ds):
    """Apply patch and verify images are passed through."""
    print()
    print("=" * 60)
    print("TEST 2: Patched (fix applied)")
    print("=" * 60)

    # Apply the fix
    import importlib
    import mlx_vlm.trainer.datasets
    importlib.reload(mlx_vlm.trainer.datasets)
    import scripts.fix_mlxvlm_datasets  # noqa: F401

    from mlx_vlm.trainer.datasets import VisionDataset as PatchedVisionDataset
    dataset = PatchedVisionDataset(ds, config, processor)
    item = dataset[0]

    pv = item.get("pixel_values")
    ids = item.get("input_ids")

    fix_works = pv is not None
    print(f"  pixel_values: {'NONE (STILL BROKEN!)' if not fix_works else f'shape {pv.shape}'}")
    print(f"  input_ids tokens: {ids.shape[-1]}")

    if fix_works:
        print(f"  FIX WORKS — pixel_values present, tokens expanded to {ids.shape[-1]}")
    return fix_works


def main():
    model, processor, config, ds = load_model_and_data()
    print(f"  model_type: {config.get('model_type')}\n")

    bug_confirmed = test_unpatched(model, processor, config, ds)
    fix_works = test_patched(model, processor, config, ds)

    print()
    print("=" * 60)
    if bug_confirmed and fix_works:
        print("PASS: Bug reproduced and fix validated")
    elif not bug_confirmed:
        print("SKIP: Bug not present in this mlx-vlm version")
    else:
        print("FAIL: Fix did not work")
    print("=" * 60)


if __name__ == "__main__":
    main()
