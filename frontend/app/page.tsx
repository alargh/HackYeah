"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { StatusBadge } from "@/components/StatusBadge";
import { api } from "@/lib/api";
import { QUALITIES } from "@/lib/quality";
import type { LessonSummary } from "@/types";

const DEMO_PROBLEM =
  "Danych jest 5 różnych osób: A,B,C,D,E.\nOsoby te ustawiają się w jednym szeregu.\nIle istnieje różnych sposobów ustawienia tych osób,\njeśli osoby A i B nie mogą stać obok siebie?";
const DEMO_SCOPE = "Use only permutations, factorials and the multiplication rule.";

export default function HomePage() {
  const router = useRouter();
  const [problem, setProblem] = useState("");
  const [scope, setScope] = useState("");
  const [quality, setQuality] = useState("l");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lessons, setLessons] = useState<LessonSummary[]>([]);
  const [gemini, setGemini] = useState<boolean | null>(null);

  useEffect(() => {
    api.listLessons().then(setLessons).catch(() => setLessons([]));
    api.health().then((h) => setGemini(h.gemini_configured)).catch(() => setGemini(null));
  }, []);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const { lesson_id } = await api.createLesson(problem.trim(), scope.trim() || undefined, quality);
      router.push(`/lessons/${lesson_id}`);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto grid max-w-5xl gap-6 lg:grid-cols-[1fr_320px]">
      <section className="card p-6">
        <h1 className="text-2xl font-bold">Tutorly</h1>
        <p className="mt-1 text-slate-600">
          Enter a problem. Tutorly analyses it, solves it within your knowledge scope, verifies the result with
          Python, and builds an animated, narrated lesson.
        </p>

        {gemini === false && (
          <div className="mt-4 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800">
            The backend has no <code>GEMINI_API_KEY</code>. Set it in <code>.env</code> and restart the backend.
          </div>
        )}

        <label className="label mt-6 block" htmlFor="problem">
          Problem
        </label>
        <textarea
          id="problem"
          className="mt-1 h-40 w-full rounded-lg border border-slate-300 p-3 font-mono text-sm focus:border-lens-500 focus:outline-none"
          placeholder="e.g. In how many ways can 5 people stand in a row if A and B may not stand next to each other?"
          value={problem}
          onChange={(e) => setProblem(e.target.value)}
        />

        <label className="label mt-4 block" htmlFor="scope">
          Knowledge scope <span className="normal-case text-slate-400">(optional)</span>
        </label>
        <textarea
          id="scope"
          className="mt-1 h-20 w-full rounded-lg border border-slate-300 p-3 text-sm focus:border-lens-500 focus:outline-none"
          placeholder="e.g. Use only permutations, factorials and the multiplication rule."
          value={scope}
          onChange={(e) => setScope(e.target.value)}
        />

        <label className="label mt-4 block" htmlFor="quality">
          Video quality
        </label>
        <select
          id="quality"
          className="mt-1 rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
          value={quality}
          onChange={(e) => setQuality(e.target.value)}
        >
          {QUALITIES.map((q) => (
            <option key={q.value} value={q.value}>
              {q.label}
            </option>
          ))}
        </select>

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <button className="btn-primary" disabled={busy || problem.trim().length < 3} onClick={submit}>
            {busy ? "Starting…" : "Generate lesson"}
          </button>
          <button
            className="btn-ghost"
            onClick={() => {
              setProblem(DEMO_PROBLEM);
              setScope(DEMO_SCOPE);
            }}
          >
            Load demo problem
          </button>
        </div>
        {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
      </section>

      <aside className="card p-4">
        <h2 className="label">Recent lessons</h2>
        <ul className="mt-2 space-y-2">
          {lessons.length === 0 && <li className="text-sm text-slate-400">No lessons yet.</li>}
          {lessons.map((l) => (
            <li key={l.id}>
              <Link href={`/lessons/${l.id}`} className="block rounded-lg p-2 hover:bg-slate-50">
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-sm font-medium">{l.title || l.problem_text.slice(0, 48)}</span>
                  <StatusBadge status={l.status} />
                </div>
                <span className="text-xs text-slate-400">{new Date(l.created_at).toLocaleString()}</span>
              </Link>
            </li>
          ))}
        </ul>
      </aside>
    </div>
  );
}
