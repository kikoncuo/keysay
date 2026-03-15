# CLAUDE.md

## Git workflow

Never commit directly to `main`. All changes go through pull requests:

1. Create a feature branch from `main`
2. Make changes and commit to the branch
3. Push the branch and create a PR via `gh pr create`
4. Merge the PR via `gh pr merge --merge`

```bash
# Example workflow
git checkout main && git pull
git checkout -b fix/description
# ... make changes ...
git add <files> && git commit -m "description"
git push -u origin fix/description
gh pr create --base main --title "description" --body "summary"
gh pr merge --merge
```

## Project structure

- `keysay/` — Main app code (PyQt6 UI, ASR, VLM, hotkey, paste)
- `scripts/` — Training, data generation, benchmarking, and build scripts
- `vlm_training/` — Training data, adapters, and results (not in git)
- `dist/` — Built app bundle (not in git)

## Running and building

```bash
python -m keysay          # Run from source
bash scripts/build_app.sh # Build .app bundle → dist/keysay.app
open dist/keysay.app      # Launch the built app
```

After any UI or code change, rebuild and test the app before pushing:

```bash
rm -rf dist build && bash scripts/build_app.sh && open dist/keysay.app
```

## Key files

- `keysay/app.py` — Main orchestrator (hotkey → record → transcribe → paste)
- `keysay/llm/context_extractor.py` — VLM screen context extraction
- `keysay/llm/corrector.py` — Transcription correction
- `keysay/llm/_patches.py` — Transformers 5.x compatibility patches (must be imported before any model loading)
- `keysay/config.py` — Settings model and defaults

## Models

- **ASR:** Qwen3-ASR via `mlx-qwen3-asr` (MLX)
- **VLM:** Qwen3.5 via `mlx-vlm` (MLX). Uses base models, not instruct. 0.8B loops in thinking, 2B without thinking works best.
- **Correction:** Fine-tuned Qwen3.5-0.8B via `mlx_lm`

## Training

- Text correction: `mlx_lm` LoRA, 5 min on Apple Silicon
- VLM context extraction: `transformers` + PEFT on MPS (not mlx-vlm — its LoRA breaks Qwen3.5's DeltaRNN)
- Data generation uses OpenRouter API (Gemini Flash). Key in `.env` as `OPENROUTER_KEY`

## Known constraints

- Don't use Shift keys as hotkey — causes double paste due to text selection interference
- `_patches.py` must be applied before importing any mlx-vlm or transformers model loading code
- mlx-vlm LoRA on Qwen3.5 corrupts generation (3 bugs filed: images discarded, wrong alpha scaling, DeltaRNN gate instability). Use PEFT instead.
