"""Patch mlx_vlm.trainer.datasets to fix Bug 1: images discarded for Qwen models.

Root cause: VisionDataset.process() sets images=None for Qwen/Gemma/SmolVLM.
The MLX model expects unexpanded image placeholder tokens in input_ids and does
image embedding internally via merge_input_ids_with_image_features(). But the
original code passes images=None, so the image tokens get meaningless embeddings.

Fix: For Qwen models, tokenize the text prompt (keeping raw image placeholders),
and separately create pixel_values + image_grid_thw via the image processor.
The MLX model's forward pass then merges them correctly.

Usage:
    import scripts.fix_mlxvlm_datasets  # Apply patch before training
"""

import logging

log = logging.getLogger(__name__)

_applied = False


def apply_dataset_patch():
    global _applied
    if _applied:
        return
    _applied = True

    try:
        from mlx_vlm.trainer.datasets import VisionDataset, get_prompt
        from mlx_vlm.utils import prepare_inputs, process_image
        import mlx.core as mx
        import numpy as np
        import json
        import warnings

        def _patched_process(self, item):
            """Process a single item — correctly creates pixel_values for Qwen models."""

            images = item.get("images", item.get("image", []))
            if not isinstance(images, list):
                images = [images] if images else []

            audio = item.get("audio", item.get("audios", []))
            if not isinstance(audio, list):
                audio = [audio] if audio else []

            model_type = (
                self.config.get("model_type") if isinstance(self.config, dict)
                else getattr(self.config, "model_type", None)
            )

            # Support both dict and ModelConfig object
            if isinstance(self.config, dict):
                image_token_index = self.config.get("image_token_index") or self.config.get("image_token_id")
            else:
                image_token_index = getattr(self.config, "image_token_index", None) or getattr(self.config, "image_token_id", None)
            if not image_token_index:
                raise ValueError(
                    "Config must contain 'image_token_index' or 'image_token_id'"
                )

            use_embedded_images = (
                model_type.startswith("gemma")
                or model_type.startswith("qwen")
                or model_type == "smolvlm"
            )

            # Build prompts from conversations (same as original)
            conversations = item.get("messages", item.get("conversations"))
            prompts = []
            if isinstance(conversations, list) and len(conversations) > 0:
                if isinstance(conversations[0], list):
                    for conversation in conversations:
                        if model_type == "pixtral":
                            conversation = [json.loads(i) for i in conversation]
                        prompt = get_prompt(model_type, self.processor, conversation)
                        prompts.append(prompt)
                else:
                    if model_type == "pixtral":
                        conversations = [json.loads(i) for i in conversations]
                    prompt = get_prompt(model_type, self.processor, conversations)
                    prompts.append(prompt)

            if use_embedded_images and images:
                # FIX: Tokenize text normally (get_prompt already created the text
                # with image placeholder tokens). Then separately process images
                # to create pixel_values + image_grid_thw. The MLX model's forward
                # pass merges them via merge_input_ids_with_image_features().

                tokenizer = getattr(self.processor, "tokenizer", self.processor)
                if tokenizer.pad_token is None:
                    tokenizer.pad_token = tokenizer.eos_token

                # Tokenize the text prompt (contains raw <|image_pad|> tokens)
                encoded = tokenizer(
                    prompts,
                    padding=True,
                    return_tensors="np",
                    add_special_tokens=False,
                )
                input_ids = mx.array(encoded["input_ids"])
                attention_mask = mx.array(encoded["attention_mask"])

                # Process images separately to get pixel_values
                image_processor = (
                    self.processor.image_processor
                    if hasattr(self.processor, "image_processor")
                    else None
                )
                processed_images = [
                    process_image(img, self.image_resize_shape, image_processor)
                    for img in images
                ]

                # Use the HF image processor to get pixel_values + image_grid_thw
                import torch
                img_inputs = self.processor.image_processor(
                    images=processed_images,
                    return_tensors="pt",
                )

                result = {}

                # Convert pixel_values to MLX
                if "pixel_values" in img_inputs:
                    pv = img_inputs["pixel_values"]
                    result["pixel_values"] = mx.array(pv.numpy() if hasattr(pv, "numpy") else np.array(pv))

                # Get image_grid_thw and calculate correct number of image tokens
                if "image_grid_thw" in img_inputs:
                    thw = img_inputs["image_grid_thw"]
                    result["image_grid_thw"] = mx.array(thw.numpy() if hasattr(thw, "numpy") else np.array(thw))

                    # Calculate how many image tokens the vision encoder produces
                    # merge_size comes from vision config (typically 2)
                    vision_cfg = getattr(self.config, "vision_config", None)
                    if vision_cfg is None:
                        vision_cfg = self.config.get("vision_config", {}) if isinstance(self.config, dict) else {}
                    merge_size = getattr(vision_cfg, "spatial_merge_size", None)
                    if merge_size is None:
                        merge_size = vision_cfg.get("spatial_merge_size", 2) if isinstance(vision_cfg, dict) else 2
                    # n_features = prod(thw) // merge_size^2 for each image
                    n_features = 0
                    thw_np = thw.numpy() if hasattr(thw, "numpy") else np.array(thw)
                    for row in thw_np:
                        n_features += int(np.prod(row)) // (merge_size ** 2)

                    # Replace the few placeholder <|image_pad|> tokens in input_ids
                    # with the correct count of image_token_index tokens
                    ids_np = np.array(input_ids.tolist()).flatten()
                    img_token_id = image_token_index

                    # Find where image tokens are and replace with correct count
                    mask_img = ids_np == img_token_id
                    old_count = int(mask_img.sum())

                    if old_count > 0 and old_count != n_features:
                        # Build new input_ids with correct image token count
                        new_ids = []
                        inserted = False
                        for tok in ids_np:
                            if tok == img_token_id:
                                if not inserted:
                                    new_ids.extend([img_token_id] * n_features)
                                    inserted = True
                                # Skip remaining old image tokens
                            else:
                                new_ids.append(int(tok))
                        input_ids = mx.array([new_ids])
                        attention_mask = mx.ones_like(input_ids)

                # Squeeze batch dimension — VisionDataset items must be 1D
                if input_ids.ndim == 2:
                    input_ids = input_ids.squeeze(0)
                if attention_mask.ndim == 2:
                    attention_mask = attention_mask.squeeze(0)

                result["input_ids"] = input_ids
                result["attention_mask"] = attention_mask

                return result

            else:
                # Non-embedded-image models or no images: original behavior
                inputs = prepare_inputs(
                    processor=self.processor,
                    images=None if use_embedded_images else (images if images else None),
                    audio=audio if audio else None,
                    prompts=prompts,
                    image_token_index=image_token_index,
                    resize_shape=self.image_resize_shape,
                )

                return {
                    "pixel_values": inputs.get("pixel_values"),
                    "input_ids": inputs["input_ids"],
                    "attention_mask": inputs.get(
                        "attention_mask", mx.ones_like(inputs["input_ids"])
                    ),
                    **{
                        k: v
                        for k, v in inputs.items()
                        if k not in ["input_ids", "pixel_values", "attention_mask"]
                    },
                }

        VisionDataset.process = _patched_process
        log.info("Patched VisionDataset.process to pass images for all model types")

    except Exception as e:
        log.warning("Failed to patch VisionDataset: %s", e)


apply_dataset_patch()
