"use client";

import { useEffect, useRef, useState } from "react";

type Status =
  | { phase: "idle" }
  | { phase: "submitting" }
  | { phase: "queued"; runId: number }
  | { phase: "running"; runId: number; startedAt: number }
  | { phase: "ready"; downloadUrl: string; releaseUrl: string }
  | { phase: "error"; message: string };

const DURATIONS = [15, 30, 45, 60, 90];

export default function Home() {
  const [book, setBook] = useState("");
  const [duration, setDuration] = useState(30);
  const [status, setStatus] = useState<Status>({ phase: "idle" });
  const pollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (pollTimer.current) clearTimeout(pollTimer.current);
    };
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!book.trim()) return;
    setStatus({ phase: "submitting" });

    try {
      const res = await fetch("/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ book: book.trim(), duration }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Failed to start generation");

      setStatus({ phase: "queued", runId: data.runId });
      poll(data.runId, Date.now());
    } catch (err: unknown) {
      setStatus({ phase: "error", message: err instanceof Error ? err.message : "Unknown error" });
    }
  }

  async function poll(runId: number, startedAt: number) {
    try {
      const res = await fetch(`/api/status/${runId}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Status check failed");

      if (data.status === "completed" && data.conclusion === "success" && data.downloadUrl) {
        setStatus({ phase: "ready", downloadUrl: data.downloadUrl, releaseUrl: data.releaseUrl });
        return;
      }
      if (data.status === "completed" && data.conclusion !== "success") {
        setStatus({ phase: "error", message: `Workflow ${data.conclusion}. Check the Action logs.` });
        return;
      }

      setStatus({ phase: "running", runId, startedAt });
      pollTimer.current = setTimeout(() => poll(runId, startedAt), 8000);
    } catch (err: unknown) {
      setStatus({ phase: "error", message: err instanceof Error ? err.message : "Unknown error" });
    }
  }

  const elapsedMin =
    status.phase === "running"
      ? Math.floor((Date.now() - status.startedAt) / 60000)
      : 0;
  const elapsedSec =
    status.phase === "running"
      ? Math.floor(((Date.now() - status.startedAt) % 60000) / 1000)
      : 0;

  return (
    <main className="mx-auto max-w-xl px-6 py-16 sm:py-24">
      <header className="mb-10">
        <h1 className="text-4xl font-bold tracking-tight sm:text-5xl">
          📚 → 🎬 <span className="text-gold">Book Reel</span>
        </h1>
        <p className="mt-3 text-zinc-400">
          Type any non-fiction book. Get a vertical Instagram Reel summary with voiceover.
        </p>
      </header>

      <form onSubmit={handleSubmit} className="space-y-5 rounded-2xl border border-zinc-800 bg-zinc-950/60 p-6">
        <div>
          <label htmlFor="book" className="block text-sm font-medium text-zinc-300">
            Book title
          </label>
          <input
            id="book"
            type="text"
            placeholder="e.g. Atomic Habits"
            value={book}
            onChange={(e) => setBook(e.target.value)}
            required
            disabled={status.phase !== "idle" && status.phase !== "error"}
            className="mt-2 w-full rounded-lg border border-zinc-700 bg-zinc-900 px-4 py-3 text-base placeholder-zinc-500 focus:border-gold focus:outline-none focus:ring-1 focus:ring-gold disabled:opacity-60"
          />
        </div>

        <div>
          <label htmlFor="duration" className="block text-sm font-medium text-zinc-300">
            Duration
          </label>
          <select
            id="duration"
            value={duration}
            onChange={(e) => setDuration(Number(e.target.value))}
            disabled={status.phase !== "idle" && status.phase !== "error"}
            className="mt-2 w-full rounded-lg border border-zinc-700 bg-zinc-900 px-4 py-3 text-base focus:border-gold focus:outline-none focus:ring-1 focus:ring-gold disabled:opacity-60"
          >
            {DURATIONS.map((d) => (
              <option key={d} value={d}>{d} seconds</option>
            ))}
          </select>
        </div>

        <button
          type="submit"
          disabled={status.phase !== "idle" && status.phase !== "error"}
          className="w-full rounded-lg bg-gold px-6 py-3 text-base font-bold text-ink transition hover:bg-gold-soft disabled:cursor-not-allowed disabled:opacity-60"
        >
          {status.phase === "idle" || status.phase === "error" ? "Generate reel" : "Working..."}
        </button>
      </form>

      <section className="mt-8">
        {status.phase === "submitting" && (
          <div className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-5 text-zinc-300">
            Submitting your request...
          </div>
        )}

        {status.phase === "queued" && (
          <div className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-5 text-zinc-300">
            Workflow queued. Run #{status.runId}.
          </div>
        )}

        {status.phase === "running" && (
          <div className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-5">
            <p className="text-zinc-300">
              Generating your reel... usually takes 3-5 minutes. (Run #{status.runId})
            </p>
            <p className="mt-1 text-sm text-zinc-500">
              Elapsed: {elapsedMin}m {elapsedSec}s
            </p>
            <div className="mt-4 h-2 w-full overflow-hidden rounded-full bg-zinc-800">
              <div className="h-full w-1/3 animate-pulse rounded-full bg-gold" />
            </div>
          </div>
        )}

        {status.phase === "ready" && (
          <div className="rounded-xl border border-gold/40 bg-gold/5 p-5">
            <p className="text-lg font-semibold text-gold">Your reel is ready 🎉</p>
            <a
              href={status.downloadUrl}
              className="mt-3 inline-block rounded-lg bg-gold px-5 py-2.5 font-bold text-ink hover:bg-gold-soft"
            >
              ↓ Download MP4
            </a>
            <a
              href={status.releaseUrl}
              target="_blank"
              rel="noreferrer"
              className="ml-3 inline-block text-sm text-zinc-400 underline hover:text-zinc-200"
            >
              View on GitHub
            </a>
          </div>
        )}

        {status.phase === "error" && (
          <div className="rounded-xl border border-red-500/30 bg-red-500/5 p-5 text-red-300">
            <p className="font-semibold">Something went wrong.</p>
            <p className="mt-1 text-sm text-red-200/80">{status.message}</p>
          </div>
        )}
      </section>

      <footer className="mt-12 text-center text-xs text-zinc-600">
        Powered by Claude + Pexels + GitHub Actions
      </footer>
    </main>
  );
}
