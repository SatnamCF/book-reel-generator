# Book Reel Generator

Generate Instagram Reel summaries (1080×1920 MP4 with voiceover and **photorealistic AI backgrounds**) for any non-fiction book. Runs entirely on GitHub Actions — no server, no hosting fees.

Each slide is a cinematic AI-generated photo with a bold white headline overlaid, produced in seconds by chaining Claude (script + image prompts) with Gemini Imagen (the actual photos).

## How it works

1. You trigger the workflow from the **Actions** tab with a book title and a duration (15 / 30 / 45 / 60 / 90 seconds).
2. GitHub Actions runs Python that:
   - Calls **Claude (Anthropic API)** to generate a slide-by-slide script — headline + image prompt + voiceover line per slide.
   - Calls **Gemini (Google's `gemini-2.5-flash-image` model)** to turn each image prompt into a photorealistic 9:16 photo. Free tier eligible.
   - Overlays the bold white headline at the top of each photo with a dark legibility gradient.
   - Synthesizes the voiceover with `edge-tts` (Microsoft Neural voices, free, no key).
   - Stitches everything into an MP4 with a slow Ken Burns zoom (moviepy + ffmpeg).
3. The MP4 is attached to the workflow run as a downloadable artifact **and** published as a GitHub Release.

Total runtime: ~3-5 minutes per video.

## Setup (one-time)

1. **Fork or push this repo to your GitHub account.**
2. Go to **Settings → Secrets and variables → Actions → New repository secret** and add:
   - **`ANTHROPIC_API_KEY`** — Claude API key from <https://console.anthropic.com/>
   - **`GOOGLE_API_KEY`** — Gemini API key from <https://aistudio.google.com/apikey> (free tier covers ~100 images/day)
3. Done.

## Generating a reel

1. Open your repo on GitHub → **Actions** tab.
2. Pick **"Generate Book Reel"** in the left sidebar.
3. Click **"Run workflow"** (top right).
4. Enter:
   - **Book title** — e.g. `Atomic Habits`
   - **Duration** — pick from the dropdown
5. Click **Run workflow**. Wait ~3-5 minutes.
6. Download the MP4 from either:
   - The workflow run page → **Artifacts** section, or
   - The **Releases** page (every run publishes a release).

## Running it locally

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
export GOOGLE_API_KEY=...
python -m src.main "Atomic Habits" --duration 30
```

The MP4 lands in `./out/atomic_habits_30s.mp4`.

### Test without spending API calls

The included fixture uses pre-set image URLs (Lorem Picsum) so the renderer can run with zero API keys:

```bash
python -m src.main "Atomic Habits" --duration 30 \
  --content-json tests/stub_atomic_habits.json
```

### Useful CLI flags

| Flag | What it does |
|---|---|
| `--duration 15\|30\|45\|60\|90` | Target video length (default 30) |
| `--output path/to/file.mp4` | Override output path |
| `--save-content out/script.json` | Save the LLM's slide JSON for inspection |
| `--content-json path.json` | Skip the LLM call, render from a saved JSON |

## Customizing

- **Voice:** edit `VOICE` in `src/render.py` (e.g. `en-US-JennyNeural`, `en-US-AndrewNeural`)
- **Image model:** set env `REEL_IMAGE_MODEL` to `imagen-4.0-generate-001` (requires Google billing enabled) for higher fidelity than `gemini-2.5-flash-image`.
- **LLM model:** set env `REEL_MODEL` to e.g. `claude-opus-4-7` for richer scripts.
- **Headline font/sizing:** tweak `_draw_headline` in `src/render.py`.

## Cost

| Item | Cost |
|---|---|
| GitHub Actions | Free (public repo) or 2000 free min/month (private) |
| Anthropic (Claude script) | ~$0.005-0.02 per reel |
| Google Gemini (gemini-2.5-flash-image) | Free tier covers ~100 images/day |
| edge-tts voiceover | Free |
| **Total** | **~$0.02 per reel** if you stay on Gemini's free tier |

## File layout

```
.github/workflows/build_reel.yml   # workflow_dispatch entry point
src/
  llm_script.py                    # Claude → headline + image prompt + voiceover
  image_gen.py                     # Gemini Imagen → 1080x1920 photo
  render.py                        # photo + headline overlay + voice + MP4
  main.py                          # CLI
tests/stub_atomic_habits.json      # fixture (uses image URLs, no API keys needed)
requirements.txt
```
