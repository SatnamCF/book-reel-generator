import { NextResponse } from "next/server";

// Force every poll to hit GitHub fresh — never cache the response.
export const dynamic = "force-dynamic";
export const revalidate = 0;

/**
 * GET /api/status/[id]?since=<ISO_timestamp>
 *
 * Returns the newest GitHub Release that:
 *   (a) was created at or after `since` (the dispatch time), AND
 *   (b) has an .mp4 asset attached.
 *
 * If found → { ready: true, downloadUrl, releaseUrl }
 * Otherwise → { ready: false }   (client keeps polling)
 *
 * `id` (the workflow run id) is optional — used only to surface a clean
 * "workflow failed" message if the run finished with non-success.
 */
export async function GET(req: Request, { params }: { params: { id: string } }) {
  const url = new URL(req.url);
  const since = url.searchParams.get("since");
  const sinceMs = since ? new Date(since).getTime() : 0;

  const owner = process.env.GITHUB_OWNER!;
  const repo = process.env.GITHUB_REPO!;
  const pat = process.env.GITHUB_PAT!;
  if (!owner || !repo || !pat) {
    return NextResponse.json({ error: "Server misconfig" }, { status: 500 });
  }

  const auth = {
    Accept: "application/vnd.github+json",
    Authorization: `Bearer ${pat}`,
    "X-GitHub-Api-Version": "2022-11-28",
  };

  // 1. Look at the most recent releases — find the newest one created since
  //    the user's dispatch that has an MP4 attached.
  const releasesRes = await fetch(
    `https://api.github.com/repos/${owner}/${repo}/releases?per_page=20`,
    { headers: auth, cache: "no-store" },
  );
  if (!releasesRes.ok) {
    return NextResponse.json({ error: `Release lookup failed (${releasesRes.status})` }, { status: 502 });
  }
  const releases: Array<{
    body?: string;
    assets?: Array<{ name: string; browser_download_url: string }>;
    created_at?: string;
    published_at?: string;
    html_url?: string;
  }> = await releasesRes.json();

  // CRITICAL: use `published_at`, not `created_at`. GitHub's `created_at` for
  // a release is the underlying tag's commit date — when all tags point at
  // the same commit on main, they share an identical (much older) created_at.
  // `published_at` is the actual time the release went live.
  const releaseTime = (r: { published_at?: string; created_at?: string }) =>
    new Date(r.published_at || r.created_at || 0).getTime();

  const candidate = releases
    .filter((r) => {
      if (releaseTime(r) < sinceMs) return false;
      return (r.assets || []).some((a) => a.name.toLowerCase().endsWith(".mp4"));
    })
    .sort((a, b) => releaseTime(b) - releaseTime(a))[0];

  if (candidate) {
    const mp4 = (candidate.assets || []).find((a) => a.name.toLowerCase().endsWith(".mp4"))!;
    return NextResponse.json({
      ready: true,
      downloadUrl: mp4.browser_download_url,
      releaseUrl: candidate.html_url,
    });
  }

  // 2. No release yet — if we have a runId, surface failure clearly so the
  //    client doesn't poll forever.
  const runId = Number(params.id);
  if (runId && !Number.isNaN(runId)) {
    const runRes = await fetch(
      `https://api.github.com/repos/${owner}/${repo}/actions/runs/${runId}`,
      { headers: auth, cache: "no-store" },
    );
    if (runRes.ok) {
      const run = await runRes.json();
      if (run.status === "completed" && run.conclusion && run.conclusion !== "success") {
        return NextResponse.json({
          ready: false,
          failed: true,
          conclusion: run.conclusion,
          runUrl: `https://github.com/${owner}/${repo}/actions/runs/${runId}`,
        });
      }
    }
  }

  return NextResponse.json({ ready: false });
}
