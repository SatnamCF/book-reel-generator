# Book Reel Web

Friend-shareable web app that generates Instagram Reel summaries for any book.
You type a title, hit submit, and ~5 minutes later you get a vertical MP4 download link.

This `web/` folder lives **inside the same repo** as the GitHub Actions workflow that does the work. Vercel deploys this subdirectory; the workflow it triggers lives at `../.github/workflows/build_reel.yml`. One repo, one push.

## How it works

```
[friend's browser]
     ↓ POST { book, duration }
[Vercel: Next.js + serverless function]
     ↓ GitHub API (auth via your PAT, server-side only)
[GitHub Actions: build_reel.yml in this same repo]
     ↓ ~3-5 minutes
[GitHub Release with MP4 attached]
     ↓ polled by /api/status/[runId]
[friend's browser shows download link]
```

## Setup (one-time, ~5 minutes)

### 1. Push the changes to GitHub

You're already pushing the `book-reel-generator` repo. From the repo root:

```bash
git add web/
git commit -m "Add web front-end"
git push
```

The repo should already have these GitHub Secrets configured (Settings → Secrets and variables → Actions):
- `ANTHROPIC_API_KEY` — Claude key
- `PEXELS_API_KEY` — Pexels key

### 2. Create a GitHub Personal Access Token

1. Go to https://github.com/settings/tokens/new
2. Note: "Book Reel Web — workflow trigger"
3. Expiration: 1 year (or "No expiration" if you trust yourself)
4. Scopes: check `repo` AND `workflow`
5. Generate, copy the `ghp_...` value (you'll paste it into Vercel)

### 3. Deploy to Vercel

1. Go to https://vercel.com/new
2. Import your `book-reel-generator` repo
3. **IMPORTANT:** click **Edit** under "Root Directory" and set it to `web`
4. Framework: **Next.js** (auto-detected once the root directory is set)
5. Before deploying, click **Environment Variables** and add:
   - `GITHUB_OWNER` → `SatnamCF` (your GitHub username)
   - `GITHUB_REPO` → `book-reel-generator`
   - `GITHUB_WORKFLOW_FILE` → `build_reel.yml`
   - `GITHUB_PAT` → the token you generated in step 2
6. Click **Deploy**.

You'll get a URL like `book-reel-generator.vercel.app`. Share it with your friends.

## Local development

```bash
cd web
cp .env.example .env.local
# Edit .env.local with your values
npm install
npm run dev
```

Open http://localhost:3000.

## Notes / limits

- **Anyone with your URL can spend your Anthropic + Pexels tokens.** Each reel costs ~1-2 cents in API calls. Keep the URL among friends.
- **GitHub Actions free tier** gives you 2000 minutes/month for private repos (unlimited for public). Each reel uses ~5 minutes.
- **Concurrent runs** are limited by GitHub. If two friends submit at the same instant, the second run might queue briefly.

## Files

```
web/
  app/
    page.tsx              # the form + status UI
    layout.tsx
    globals.css
    api/
      generate/route.ts   # POST → triggers workflow_dispatch
      status/[id]/route.ts # GET  → polls run status + finds release MP4
  package.json
  tailwind.config.ts
  .env.example
```
