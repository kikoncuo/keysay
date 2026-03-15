# keysay

Press-to-dictate for macOS. Hold a key, speak, release — text appears wherever your cursor is.

Runs entirely on-device using [Qwen3-ASR](https://huggingface.co/Qwen/Qwen3-ASR-1.7B) on Apple Silicon via MLX. No cloud, no API keys, no latency.

## How it works

```
Hold Right Option → speak → release → text is typed into the active app
```

keysay captures audio while you hold the hotkey, transcribes it locally, and inserts the result at your cursor position using macOS Accessibility. If Accessibility insertion fails (some apps don't support it), it falls back to Cmd+V.

Optionally, keysay can screenshot your screen during recording and use a VLM to extract context — names, technical terms, jargon — that help the ASR model recognize uncommon words.

## Install

**Requirements:** macOS on Apple Silicon (M1+), Python 3.12+, 8+ GB RAM.

```bash
git clone https://github.com/kikoncuo/keysay.git
cd keysay
pip install -r requirements.txt
python -m keysay
```

First launch downloads the ASR model (~3 GB). keysay will prompt for macOS permissions: Accessibility, Microphone, Screen Recording, and Input Monitoring.

### Build the app

```bash
bash scripts/build_app.sh
# Output: dist/keysay.app
```

## Features

### Speech recognition

- **Models:** Qwen3-ASR 1.7B (best accuracy) or 0.6B (faster)
- **Quantization:** Full precision, 8-bit, or 4-bit
- **Languages:** Auto-detect, English, Spanish, Chinese, Cantonese, French, German, Italian, Japanese, Korean, Portuguese, Russian
- **Context hints:** Add custom words to improve recognition of names, jargon, and acronyms

### Screen context extraction

When enabled, keysay takes a screenshot while you're recording and feeds it to a Qwen3.5 VLM. The VLM extracts proper nouns, company names, and technical terms from whatever's on your screen — these get passed as ASR hints so the model recognizes them correctly.

VLM models (selectable in settings):

| Model | Size | RAM |
|---|---|---|
| Qwen3.5-0.8B 8-bit | 0.8B | ~3 GB |
| Qwen3.5-2B 4-bit | 2B | ~3 GB |
| Qwen3.5-4B 4-bit | 4B | ~5 GB |
| Qwen3.5-9B 4-bit | 9B | ~7 GB |

### Transcription correction

A [fine-tuned Qwen3.5-0.8B model](https://huggingface.co/Enriqueag26/keysay-transcription-cleaner-0.8B-8bit) cleans ASR output: removes self-corrections, filler words, and false starts.

```
"es a las 5, no perdon, a las 6"  →  "es a las 6"
"I um I think we should uh go"    →  "I think we should go"
```

Five correction presets: clean utterances, formal writing, email style, bullet points, code dictation. Each preset's system prompt is editable.

Details on how we fine-tuned the models: [qwen3.5-fine-tuning-guide](https://github.com/kikoncuo/qwen3.5-fine-tuning-guide)

### Text insertion

keysay remembers which app was focused when you pressed the hotkey and pastes into it after transcription. Two methods:

1. **Accessibility API** — direct text insertion via AXSelectedText (works in most native and web text fields)
2. **Clipboard fallback** — copies to clipboard and sends Cmd+V (configurable, on by default)

### Text replacements

Define find-replace pairs in settings. Applied after transcription and correction. Useful for expanding abbreviations, fixing recurring misrecognitions, or inserting special characters.

### Hotkey

Any modifier key can be the trigger. Default is Right Option. Available:

Fn/Globe, Right/Left Option, Right/Left Command, Right/Left Shift, Right/Left Control, Caps Lock

### UI

**Floating pill** — a small capsule that sits on top of all windows. Shows recording state with a live waveform, loading progress, and processing animation. Drag to reposition. Click to open settings.

**System tray** — colored dot indicates active/inactive. Menu for settings, activate/deactivate, quit.

**Settings** — tabbed window with ASR, context, VLM, correction, hotkey, advanced, and history tabs. Includes a RAM usage indicator showing estimated memory for each model.

**Transcription history** — searchable log of all transcriptions with timestamps, duration, model used, and raw vs. corrected text. Stored locally.

### Dynamic model loading

For memory-constrained systems, enable "dynamic loading" in advanced settings. Models load on demand when you press the hotkey and unload after each transcription. Trades startup latency for lower idle RAM usage.

## Architecture

```
hotkey press → capture audio + screenshot (parallel)
            → VLM extracts context terms from screenshot
            → ASR transcribes audio with context hints
            → correction model cleans transcription
            → text replacements applied
            → paste into target app
```

Everything runs on the GPU via MLX. A GPU lock serializes model operations to prevent Metal crashes from concurrent access. Audio capture, VLM extraction, and ASR run on background threads.

## Configuration

Settings persist in `~/Library/Application Support/keysay/config.json`. History in `history.json` in the same directory. Debug log at `debug.log`.

## Fine-tuning

The transcription correction model and VLM context extractor were fine-tuned using knowledge distillation from Gemini Flash. Full details, scripts, and training data: **[qwen3.5-fine-tuning-guide](https://github.com/kikoncuo/qwen3.5-fine-tuning-guide)**

During that process we found and fixed [3 bugs in mlx-vlm's LoRA training pipeline](https://github.com/Blaizzy/mlx-vlm/issues/824) that prevented VLM fine-tuning on Qwen3.5.

## License

MIT
