import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

/**
 * POST /api/generate
 * body: { book: string, duration: number }
 *
 * Triggers the GitHub Actions workflow_dispatch on the book-reel-generator
 * repo, then finds the run ID it just spawned by listing recent runs.
 *
 * Returns: { runId: number }
 */
export async function POST(req: Request) {
  const { book, duration } = await req.json().catch(() => ({}));
  if (!book || typeof book !== "string") {
    return NextResponse.json({ error: "Missing 'book' string" }, { status: 400 });
  }
  if (!duration || typeof duration !== "number") {
    return NextResponse.json({ error: "Missing 'duration' number" }, { status: 400 });
  }
  const allowed = [15, 30, 45, 60, 90];
  if (!allowed.includes(duration)) {
    return NextResponse.json({ error: "Duration must be 15, 30, 45, 60, or 90" }, { status: 400 });
  }

  const owner = process.env.GITHUB_OWNER!;
  const repo = process.env.GITHUB_REPO!;
  const workflow = process.env.GITHUB_WORKFLOW_FILE || "build_reel.yml";
  const pat = process.env.GITHUB_PAT!;
  if (!owner || !repo || !pat) {
    return NextResponse.json(
      { error: "Server misconfig: GITHUB_OWNER / GITHUB_REPO / GITHUB_PAT must be set" },
      { status: 500 },
    );
  }

  const dispatchedAt = new Date();
  // Subtract a small buffer so we don't miss the run by a clock skew of a few seconds
  const lookbackTime = new Date(dispatchedAt.getTime() - 30_000).toISOString();

  // 1. Trigger workflow_dispatch
  const dispatchRes = await fetch(
    `https://api.github.com/repos/${owner}/${repo}/actions/workflows/${workflow}/dispatches`,
    {
      method: "POST",
      headers: {
        Accept: "application/vnd.github+json",
        Authorization: `Bearer ${pat}`,
        "X-GitHub-Api-Version": "2022-11-28",
      },
      body: JSON.stringify({
        ref: "main",
        inputs: { book, duration: String(duration) },
      }),
    },
  );

  if (!dispatchRes.ok) {
    const text = await dispatchRes.text();
    return NextResponse.json(
      { error: `GitHub dispatch failed (${dispatchRes.status}): ${text}` },
      { status: 502 },
    );
  }

  // 2. Poll runs API to find the run we just triggered.
  // GitHub takes a moment to register the dispatched run — try for ~10s.
  let runId: number | null = null;
  for (let attempt = 0; attempt < 6; attempt++) {
    await new Promise((r) => setTimeout(r, 1500));
    const runsRes = await fetch(
      `https://api.github.com/repos/${owner}/${repo}/actions/runs?event=workflow_dispatch&per_page=5&created=%3E${encodeURIComponent(lookbackTime)}`,
      {
        headers: {
          Accept: "application/vnd.github+json",
          Authorization: `Bearer ${pat}`,
          "X-GitHub-Api-Version": "2022-11-28",
        },
      },
    );
    if (!runsRes.ok) continue;
    const runsData = await runsRes.json();
    const candidate = (runsData.workflow_runs || [])
      .filter((r: { path?: string }) => r.path?.endsWith(`/${workflow}`))
      .sort(
        (a: { created_at: string }, b: { created_at: string }) =>
          new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
      )[0];
    if (candidate && new Date(candidate.created_at).getTime() >= dispatchedAt.getTime() - 10_000) {
      runId = candidate.id;
      break;
    }
  }

  if (!runId) {
    return NextResponse.json(
      { error: "Workflow dispatched but couldn't locate the run ID (try refreshing in a moment)" },
      { status: 504 },
    );
  }

  return NextResponse.json({ runId });
}
