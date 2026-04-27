import { NextResponse } from "next/server";

/**
 * GET /api/status/[id]
 *
 * Polls the workflow run status. Once complete and successful, finds the
 * matching GitHub Release (auto-published by the workflow) and returns its
 * MP4 download URL.
 */
export async function GET(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const runId = Number(id);
  if (!runId || Number.isNaN(runId)) {
    return NextResponse.json({ error: "Invalid run id" }, { status: 400 });
  }

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

  // 1. Run status
  const runRes = await fetch(`https://api.github.com/repos/${owner}/${repo}/actions/runs/${runId}`, { headers: auth });
  if (!runRes.ok) {
    return NextResponse.json({ error: `Run lookup failed (${runRes.status})` }, { status: 502 });
  }
  const run = await runRes.json();

  if (run.status !== "completed") {
    return NextResponse.json({ status: run.status, conclusion: null });
  }
  if (run.conclusion !== "success") {
    return NextResponse.json({ status: "completed", conclusion: run.conclusion });
  }

  // 2. Find the release the workflow just published — match by run_id in body
  const releasesRes = await fetch(
    `https://api.github.com/repos/${owner}/${repo}/releases?per_page=15`,
    { headers: auth },
  );
  if (!releasesRes.ok) {
    return NextResponse.json({ error: `Release lookup failed (${releasesRes.status})` }, { status: 502 });
  }
  const releases = await releasesRes.json();
  // The workflow body includes `Run: ${{ github.run_id }}` — find the matching one
  const release = releases.find((r: { body?: string }) => r.body?.includes(`Run: ${runId}`));
  if (!release) {
    // Release publishes a moment after the run completes — tell the client to keep polling
    return NextResponse.json({ status: "completed", conclusion: "success", downloadUrl: null });
  }

  const mp4 = (release.assets || []).find((a: { name: string }) => a.name.endsWith(".mp4"));
  if (!mp4) {
    return NextResponse.json({ error: "Release found but no MP4 asset attached" }, { status: 502 });
  }

  return NextResponse.json({
    status: "completed",
    conclusion: "success",
    downloadUrl: mp4.browser_download_url,
    releaseUrl: release.html_url,
  });
}
