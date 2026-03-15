#!/usr/bin/env python3
"""Benchmark correction LLM models: load time, RAM, tokens/sec."""

import gc
import os
import time

import mlx.core as mx

MODELS = [
    "mlx-community/Qwen3-0.6B-8bit",
    "mlx-community/Qwen3-1.7B-4bit",
    "mlx-community/Qwen3-1.7B-8bit",
    "mlx-community/Qwen3-4B-4bit",
    "mlx-community/Qwen3-4B-8bit",
    "mlx-community/Qwen3-8B-4bit",
]

SAMPLE_PROMPT = (
    "You are a speech-to-text post-processor. Clean up the transcribed speech "
    "by removing filler words, self-corrections, and false starts. "
    "Output ONLY the cleaned text."
)
SAMPLE_INPUT = (
    "vale probando, no espera, quiero decir que la televisión está apagada"
)


def get_ram_mb() -> float:
    """Get current process RSS in MB."""
    import resource
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024)


def benchmark_model(model_id: str) -> dict:
    from mlx_lm import load, stream_generate

    gc.collect()
    mx.metal.clear_cache()

    ram_before = get_ram_mb()
    t0 = time.perf_counter()
    model, tokenizer = load(model_id)
    load_time = time.perf_counter() - t0
    ram_after = get_ram_mb()

    messages = [
        {"role": "system", "content": SAMPLE_PROMPT},
        {"role": "user", "content": f"Transcription: {SAMPLE_INPUT}"},
    ]
    prompt = tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True,
        enable_thinking=False,
    )

    # Warm up
    tokens = []
    for resp in stream_generate(model, tokenizer, prompt=prompt, max_tokens=5):
        tokens.append(resp.text)

    # Benchmark
    tokens = []
    t0 = time.perf_counter()
    for resp in stream_generate(model, tokenizer, prompt=prompt, max_tokens=200):
        tokens.append(resp.text)
    gen_time = time.perf_counter() - t0

    output = "".join(tokens)
    n_tokens = len(tokens)
    tps = n_tokens / gen_time if gen_time > 0 else 0

    # Cleanup
    del model, tokenizer
    gc.collect()
    mx.metal.clear_cache()

    return {
        "model": model_id,
        "load_time_s": load_time,
        "ram_delta_mb": ram_after - ram_before,
        "tokens": n_tokens,
        "gen_time_s": gen_time,
        "tokens_per_sec": tps,
        "output": output.strip(),
    }


def main():
    print(f"{'Model':<45} {'Load(s)':>8} {'RAM(MB)':>8} {'Tok/s':>8} {'Tokens':>7}")
    print("-" * 85)

    for model_id in MODELS:
        print(f"\nBenchmarking {model_id}...")
        try:
            result = benchmark_model(model_id)
            print(
                f"{result['model']:<45} "
                f"{result['load_time_s']:>7.1f}s "
                f"{result['ram_delta_mb']:>7.0f}  "
                f"{result['tokens_per_sec']:>7.1f}  "
                f"{result['tokens']:>6}"
            )
            print(f"  Output: {result['output'][:120]}")
        except Exception as e:
            print(f"  ERROR: {e}")

    print("\nDone.")


if __name__ == "__main__":
    main()
