# Book Reel Generator

Generate Instagram Reel summaries (1080×1920 MP4 with voiceover) for any non-fiction book. Runs entirely on GitHub Actions — no server, no hosting fees.

## How it works

1. You trigger the workflow from the **Actions** tab with a book title and a duration (15 / 30 / 45 / 60 / 90 seconds).
2. GitHub Actions runs Python that:
   - Calls **Claude (Anthropic API)** to generate a slide-by-slide script tuned to your duration.
   - Renders each slide as a 1080×1920 PNG (PIL) with one of 6 themed backgrounds (`hero_word`, `split`, `rising`, `rays`, `rings`, `silhouette`).
   - Synthesizes the voiceover with `edge-tts` (Microsoft Neural voices, free, no key).
   - Stitches everything into an MP4 with a slow Ken Burns zoom (moviepy + ffmpeg).
3. The MP4 is attached to the workflow run as a downloadable artifact **and** published as a GitHub Release.

Total runtime: ~3-5 minutes per video.

## Setup (one-time)

1. **Fork or push this repo to your GitHub account.**
2. Go to **Settings → Secrets and variables → Actions → New repository secret** and add:
   - **Name:** `ANTHROPIC_API_KEY`
   - **Value:** your Claude API key from <https://console.anthropic.com/>
3. Done. No other config needed.

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
export ANTHROPIC_API_KEY=sk-ant-...   # PowerShell: $env:ANTHROPIC_API_KEY="sk-ant-..."
python -m src.main "Atomic Habits" --duration 30
```

The MP4 lands in `./out/atomic_habits_30s.mp4`.

### Useful CLI flags

| Flag | What it does |
|---|---|
| `--duration 15\|30\|45\|60\|90` | Target video length (default 30) |
| `--output path/to/file.mp4` | Override output path |
| `--save-content out/script.json` | Save the LLM's slide JSON for inspection |
| `--content-json path.json` | Skip the LLM call, render from a saved JSON (cheap iteration) |

## Customizing

- **Voice:** edit `VOICE` in `src/render.py` (e.g. `en-US-JennyNeural`, `en-US-AndrewNeural`)
- **Speech pace:** the rate is auto-calculated to fit the duration; cap range in `_calc_rate`
- **Themes:** add a new background function to `src/themes.py` and register it in the `THEMES` dict + the `theme` enum in the LLM prompt (`src/llm_script.py`)
- **Model:** set repo variable `REEL_MODEL` to e.g. `claude-opus-4-7` for higher quality (more cost)

## Cost

- GitHub Actions: free for public repos, 2000 free minutes/month for private.
- Anthropic: ~$0.005-0.02 per reel with `claude-sonnet-4-5`.
- edge-tts: free.
- Total: roughly **a cent or two per video**.

## File layout

```
.github/workflows/build_reel.yml   # workflow_dispatch entry point
src/
  llm_script.py                    # Claude → slide JSON
  themes.py                        # 6 reusable PIL backgrounds
  render.py                        # slides + voice + MP4
  main.py                          # CLI
requirements.txt
```
