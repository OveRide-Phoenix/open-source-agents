# Event Photo Curator

> Turn an event photo folder into a selection of original files, suggested social captions, and an auditable contact sheet with one command.

## Overview

### Problem Statement & Intended Users

Event photographers and community organizers need to review repetitive bursts, technical failures, and hundreds of potential social posts. This CLI handles the complete selection workflow: inspect the folder, filter technical failures, keep a burst representative, rank survivors, copy the best originals, and explain every decision in CSV and HTML.

### Key Features

- JPEG, PNG, HEIC/HEIF, and optional Fujifilm RAF embedded-JPEG loading; EXIF orientation is respected.
- Local blur/exposure checks and perceptual duplicate groups before any paid API request.
- Gemini vision rates moment, composition, and expressions independently from 1–10, explains the judgment, and suggests a short caption. The final score is their arithmetic mean. When no people are visible, the prompt asks for a neutral expressions score of 5.
- Explicit offline mock mode, bounded batch/retry processing, content-addressed caching, untouched originals, original-file copies, and an HTML contact sheet of picks **and** rejects.

## Technical Stack

- **Language & runtime:** Python 3.11+.
- **Agent framework:** custom bounded Python workflow; Typer CLI and Rich progress/summary. No external agent orchestration service is required.
- **Image processing:** Pillow, pillow-heif, OpenCV headless, NumPy, ImageHash.
- **Models:** configurable Gemini model, default `gemini-2.5-flash`, via `google-genai`. Offline `MockProvider` uses sharpness only and makes no AI judgment.
- **External APIs:** Gemini API only when the Gemini provider has a configured key. `python-dotenv` loads configuration. Optional `rawpy` extracts RAF previews; it does not demosaic RAW data.

## Architecture & Data Flow

```text
Input folder (read-only, non-recursive)
  → decode/orient/downscale preview to max 1024px
  → Laplacian sharpness + grayscale exposure histogram
  → perceptual-hash connected groups → sharpest eligible representative
  → surviving candidates only
  → matching local cache OR batched Gemini vision / offline mock
  → validate scores and IDs → save completed batches to cache
  → rank → copy top N originals → report.csv + report.html → stop
```

The deterministic stages are cheap and remove frames that do not need subjective evaluation. The AI scope is visual editorial judgment: timing/story, framing, and expressions, plus captions. It does not need to choose the files to open or invent tool calls; Python enforces the workflow and safety boundaries. The processing loop runs until all survivor batches finish, with at most five attempts per batch for rate limits/transient server errors. It then exports the complete result without manual file sorting. There is no unbounded reflection loop or extra paid pass over already scored photos.

Gemini receives labelled, metadata-free JPEG previews, **not** the source RAF/HEIC/full-resolution files. Each response must contain exactly the expected IDs and valid 1–10 criteria; malformed output stops the run rather than inventing scores. Completed batches remain cached for a later retry.

## Prerequisites

- Python 3.11 or newer and `pip` with virtual-environment support.
- A supported photo folder and disk space for copies of selected originals.
- For Gemini: network access and a valid Gemini API key with access/quota for the chosen vision model. Mock mode needs neither.
- HEIC requires the declared `pillow-heif` dependency and its platform codec support. Optional RAF loading requires a compatible `rawpy` installation and a camera file containing an embedded JPEG preview.

## Installation & Setup

From a clean clone (macOS/Linux shell commands):

```bash
git clone https://github.com/gdgcblr/open-source-agents.git
cd open-source-agents/agents/event-photo-curator
# This directory is available after the contribution is merged.
# Before then, clone the contributor fork and check out feat/event-photo-curator.
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Before upstream merge, use this source instead of the first two commands:

```bash
git clone --branch feat/event-photo-curator https://github.com/OveRide-Phoenix/open-source-agents.git
cd open-source-agents/agents/event-photo-curator
```

For optional RAF support:

```bash
python -m pip install 'rawpy>=0.24,<1'
```

Set `GEMINI_API_KEY` in the local `.env` file or export it in your shell. Never commit `.env`. No key is needed for `--provider mock`. Run commands from this project directory so Python can find the `curator` package. The module is self-contained; no root-level dependencies are required.

## Configuration & Environment Variables

| Variable | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `GEMINI_API_KEY` | For Gemini vision | Unset | Loaded from the working directory's `.env`, without overriding an existing environment variable. Missing/placeholder keys produce a clear warning and switch to mock. Invalid real keys cause a visible failure; they do not silently switch providers. |

| CLI option | Default | Meaning |
| :--- | :--- | :--- |
| `--out` | `./picks` | Separate, new or empty destination; never overwrites an existing selection. |
| `--top` | `15` | Maximum number to copy; fewer if fewer candidates survive. |
| `--provider` | `gemini` | `gemini` for visual AI ranking or `mock` for offline sharpness ranking. |
| `--model` | `gemini-2.5-flash` | Gemini model with image input and JSON-schema output support. |
| `--blur-threshold` | `100` | Reject when variance of Laplacian is below this value, measured on a grayscale preview with longest edge at most 1024px. |
| `--exposure-percent` | `20` | Reject when more than this percentage of grayscale pixels are at least 250 (highlights) or at most 5 (shadows). Use 100 to disable exposure rejection. |
| `--dup-distance` | `6` | Maximum Hamming distance between 64-bit pHashes to link near-duplicates; 0 matches equal hashes only. |
| `--batch-size` | `5` | Images per Gemini request, 1–16. Sequential batches keep request bursts bounded. |
| `--cache-dir` | `./.cache` | Local per-image assessment cache, shared across output folders. |
| `--caption-style` | `Casual event Instagram, no hashtag spam` | Style guidance for Gemini captions; mock captions are fixed placeholders. |

Cache keys include the source file's SHA-256, provider, model, caption style, and pipeline version. Changing the model/style/file invalidates the relevant cache entry. Changing `--top` or filter thresholds reuses still-relevant assessments. Cache files contain scores/reasons/captions but no API keys or images. Unchanged, fully cached reruns make zero model calls and use zero new model tokens; local decoding/filtering still runs. Use a **new output folder** for each rerun, or move the previous output yourself. Do not delete the cache if you want to reuse scores.

## How to Run

```bash
python -m curator run ./photos --out ./picks --top 15 \
  --provider gemini --blur-threshold 100 --dup-distance 6 \
  --caption-style "GDG Cloud Bengaluru Instagram, casual, no hashtag spam"
```

Offline, with no network or API key:

```bash
python -m curator run ./photos --out ./picks-offline --provider mock
```

Open `picks/report.html` directly in a browser. It embeds previews for every readable pick/reject, works offline, identifies the provider/model, shows criterion scores for Gemini-ranked photos, and links to copied originals. RAF/HEIC previews display as JPEG; copied files retain their original format. `report.csv` has:

```text
filename,sharpness,exposure flag,duplicate group,ai score,reason,caption,picked
```

The mock score is `1 + 9 × sharpness / (sharpness + 1000)`, rounded to two decimals. Its reason and caption explicitly identify mock behavior. Mock output is useful for checking the workflow, not for judging moments or expressions.

### Cost and efficiency

Only surviving uncached images are uploaded. Five images share one prompt by default; this is synchronous multi-image batching, not the discounted Gemini Batch API. Images have a maximum 1024px edge, and results are cached immediately after each completed batch. Rate limits and HTTP 500/502/503/504 get exponential backoff plus jitter (at most five attempts). Other API errors stop immediately. Requests have a 120-second SDK timeout. For `gemini-2.5-flash` and `gemini-2.5-flash-lite`, thinking is disabled and response tokens are capped at `max(1024, 512 × batch image count)` to bound overhead. Other model names keep their own generation defaults; they may consume more tokens.

The summary's **Estimated tokens used** is the sum of `usage_metadata.total_token_count` from successful responses in this run, or 0 if metadata is absent. This is a usage indicator, not a dollar quote or a full billing ledger; failed requests may also incur costs. Mock/cached runs consume no new model tokens. Actual prices and quotas depend on your account/model: see [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing). Check [model capabilities](https://ai.google.dev/gemini-api/docs/models/gemini-2.5-flash) before overriding `--model`; a text-only or JSON-incompatible model will fail. No model fallback spends money on another model automatically.

## Example Input & Output

### Example Input

These six images are generated color patterns, not people or private event photographs. They demonstrate technical filtering and output mechanics; they cannot validate visual editorial quality.

```bash
python tests/generate_sample.py sample-photos
python -m curator run sample-photos --out sample-output-final --top 2 \
  --provider mock --cache-dir .cache/example \
  --caption-style "GDG Cloud Bengaluru Instagram, casual, no hashtag spam"
```

### Example Output

Captured from the actual macOS/Python 3.12 mock run (progress-bar glyphs omitted and output path abbreviated):

```text
Provider: mock | Model: sharpness-v1
       Event Photo Curator
┏━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━┓
┃ Metric                ┃ Count ┃
┡━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━┩
│ Scanned               │     6 │
│ Blurry                │     1 │
│ Dupes                 │     2 │
│ Exposure issues       │     1 │
│ Unreadable            │     0 │
│ Picked                │     2 │
│ Cache hits            │     0 │
│ Estimated tokens used │     0 │
└───────────────────────┴───────┘
Output: ./sample-output-final (absolute path shown on your machine)
```

Two selected originals, `report.csv`, and `report.html` are written. There are three eligible ranking candidates; the third is rejected as outside the top two. Blurry/duplicate counts overlap because the blurred image also belongs to the burst. All six rows include a reason. The selected copies are byte-for-byte identical to their inputs.

The Gemini adapter is tested with simulated structured responses, reordered IDs, rate limits, and malformed output. **A real Gemini call and editorial quality on real event photos have not been verified.** No AI-generated output is presented here as a genuine live run.

## How to Test

```bash
python -m pip install 'pytest>=8,<10'
python -m pytest -q
```

Tests generate their own images in temporary folders. They cover sharpness versus blur, exposure, connected duplicate groups and eligible sharpest selection, mock scores, HEIC round-trip decoding, metadata/orientation handling, RAF adapter behavior with a simulated decoder, batch/caching behavior, 429 backoff, bounded failures, malformed Gemini output, CLI execution, rejected-file explanations, input/output isolation, source/copy hashes, CSV formula protection, and HTML escaping. Tests do not use a real API key or send network requests.

Browser verification uses the generated HTML report; no browser dependency is needed to run the CLI or Python tests.

## Known Limitations

- Blur thresholds vary with sensor/lens, preview size, subject motion, sharpening, and intentional bokeh. A sharp background can conceal a blurry face. Tune against your own files.
- Exposure uses grayscale clipping percentages, not a per-channel RAW histogram or subject-aware lighting assessment. Intentional dark/bright scenes can be rejected. Filtered-out frames never reach Gemini.
- Duplicate detection compares every readable pair: O(n²). Connected groups can chain together photos whose endpoints exceed the threshold. This is similarity grouping, not capture-time-aware burst recognition; visually similar separate moments can be grouped. The sharpest technically eligible frame wins before AI evaluates expressions.
- The AI taste/captions are subjective and may hallucinate details despite the prompt. Small expressions may be hard to assess at 1024px. Independent batch scores can drift; review the contact sheet before publishing.
- Scans one directory, not subfolders. Symlink inputs are skipped. Unsupported files are ignored; corrupt/unsupported previews appear as unreadable rejects. If all photos fail filters, reports are still produced with zero picks.
- RAF preview quality depends on the camera JPEG. Full RAW rendering and camera color profiles are out of scope. The RAF adapter is tested with a simulated decoder; no real Fujifilm RAF file was available for validation.
- Holds compressed previews for the contact sheet in memory; very large events increase memory use and HTML size. Original decoding can briefly need substantially more memory than the preview.
- A missing/placeholder key warns and uses mock; a key's mere presence does not prove successful Gemini access. Invalid responses or exhausted retries stop before export. Already completed score batches stay cached. If copying/report writing fails, a partial output may remain; originals are untouched and the next run requires a new/empty output directory.
- The output must be separate from the entire input tree. Copies are never overwritten. There is no automatic cleanup or deletion of prior outputs.
- Dependencies use bounded version ranges rather than a lockfile; future compatible releases can behave differently.
- Tested on macOS with Python 3.11 and 3.12, including a fresh isolated Python 3.11 environment installed from the staged contribution files. Linux, Windows, real RAF decoding, real Gemini vision calls, and real event selection quality are unverified.

## Security & Privacy Considerations

- Keys stay in environment variables or untracked `.env`. Provider error messages are sanitized; raw exceptions that might contain credentials are not printed.
- Only Gemini mode uploads resized previews of survivors to Google. Use it only for photos you have permission to process; review the service's applicable data policies. Mock mode stays local.
- Previews are re-encoded without EXIF/GPS metadata. **Selected originals are copied unchanged, including any metadata**, so review them before public sharing.
- The cache and reports can contain image descriptions/captions; HTML embeds readable previews of rejected photos too. Keep them private if the event photos are private. Only share the selected files when that is what you intend.
- HTML escapes filenames/model text; CSV neutralizes leading spreadsheet formula characters. No arbitrary shell execution, source edits, source deletions, publishing, or face identification are performed.
- `.gitignore` excludes secrets, environments, caches, generated outputs, and photo formats. Tests and the example generator use no personal photos.

## Future Improvements

- Candidate improvements after measuring on real events: indexed duplicate lookup for large folders and a subject-aware blur assessment.
- A locally hosted multimodal Gemma provider could provide offline visual judgment, but requires a separate model runtime and validation of image/schema support; it is not included in this short build.
- There are no required deferred implementation steps for the current CLI workflow; real Gemini/camera validation remains necessary before relying on editorial quality.

## License

This project is contributed under the repository's MIT license; see [LICENSE](../../LICENSE). No event photographs or third-party model weights are distributed.
