"use client";

import { useEffect, useMemo, useState } from "react";

import { api, BUSY } from "@/lib/api";
import type { Job, Lesson } from "@/types";

/** Lesson-level stages, in pipeline order. */
const GLOBAL = [
  { stage: "analyze_problem", label: "Analiza zadania" },
  { stage: "compile_scope", label: "Zakres wiedzy" },
  { stage: "reason", label: "Rozwiązanie + weryfikacja" },
  { stage: "plan_lesson", label: "Plan lekcji" },
];
/** Per-scene stages, in pipeline order (several job stages may feed one column). */
const SCENE = [
  { key: "narration", label: "Narracja", stages: ["narration"] },
  { key: "voice", label: "Głos", stages: ["tts"] },
  { key: "visual", label: "Plan wizualny", stages: ["visual_plan"] },
  { key: "code", label: "Animacja", stages: ["visual_compile", "manim_code"] },
  { key: "render", label: "Render wideo", stages: ["render"] },
];
/** A learner question answered as a video: planned by the tutor, then the same per-scene stages. */
const FOLLOWUP = [{ key: "plan", label: "Plan odpowiedzi", stages: ["ask_tutor"] }, ...SCENE];
const ACTIVE_FOLLOWUP = new Set(["PENDING", "PLANNING", "GENERATING", "GENERATED", "RENDERING"]);

function ts(s?: string | null): number | null {
  if (!s) return null;
  return Date.parse(/[zZ]|[+-]\d\d:?\d\d$/.test(s) ? s : `${s}Z`);
}

function fmt(sec: number): string {
  if (sec < 60) return `${sec.toFixed(sec < 10 ? 1 : 0)} s`;
  return `${Math.floor(sec / 60)} min ${Math.round(sec % 60)} s`;
}

type Cell = { status: "pending" | "running" | "done" | "failed"; seconds: number; calls: number; retries: number; model?: string | null };

function summarise(jobs: Job[], now: number): Cell {
  if (!jobs.length) return { status: "pending", seconds: 0, calls: 0, retries: 0 };
  let seconds = 0;
  for (const j of jobs) {
    if (j.status === "RUNNING") seconds += Math.max(0, (now - (ts(j.started_at) ?? now)) / 1000);
    else seconds += (j.duration_ms ?? 0) / 1000;
  }
  const last = jobs[jobs.length - 1];
  const running = jobs.some((j) => j.status === "RUNNING");
  const status = running ? "running" : last.status === "FAILED" ? "failed" : "done";
  return { status, seconds, calls: jobs.length, retries: jobs.filter((j) => j.status === "FAILED").length, model: last.model };
}

const STYLE: Record<Cell["status"], string> = {
  pending: "bg-slate-100 text-slate-400",
  running: "animate-pulse bg-lens-600 text-white",
  done: "bg-emerald-100 text-emerald-800",
  failed: "bg-red-100 text-red-700",
};
const ICON: Record<Cell["status"], string> = { pending: "○", running: "◉", done: "✓", failed: "✕" };

function Chip({ label, cell, title }: { label: string; cell: Cell; title?: string }) {
  return (
    <div className={`rounded-lg px-2.5 py-1.5 text-xs ${STYLE[cell.status]}`} title={title}>
      <div className="font-medium">
        {ICON[cell.status]} {label}
      </div>
      <div className="font-mono text-[10px] opacity-80">
        {cell.status === "pending" ? "—" : fmt(cell.seconds)}
        {cell.calls > 1 ? ` · ${cell.calls}×` : ""}
        {cell.retries ? ` · ${cell.retries} ponowień` : ""}
      </div>
    </div>
  );
}

export function PipelineProgress({ lesson }: { lesson: Lesson }) {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [now, setNow] = useState(() => Date.now());
  const followupsBusy = lesson.followups.some(
    (f) => f.status !== "FAILED" && f.render_status !== "COMPLETED" && f.render_status !== "FAILED" && ACTIVE_FOLLOWUP.has(f.status),
  );
  const [open, setOpen] = useState(() => BUSY.has(lesson.status) || lesson.status === "FAILED" || followupsBusy);
  const busy = BUSY.has(lesson.status) || followupsBusy;
  useEffect(() => {
    if (followupsBusy) setOpen(true); // a new question: show its pipeline
  }, [followupsBusy]);
  const running = jobs.some((j) => j.status === "RUNNING");

  useEffect(() => {
    let alive = true;
    const load = () =>
      api
        .jobs(lesson.id)
        .then((j) => alive && setJobs(j))
        .catch(() => undefined);
    load();
    if (!busy && !running) return () => void (alive = false);
    const t = setInterval(load, 1500);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, [lesson.id, lesson.status, busy, running]);

  useEffect(() => {
    if (!running) return;
    const t = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(t);
  }, [running]);

  const sceneIds = useMemo(() => {
    const ids = lesson.scenes.map((s) => s.scene_id);
    for (const j of jobs) if (j.scene_id && !ids.includes(j.scene_id) && !lesson.followups.some((f) => f.scene_id === j.scene_id)) ids.push(j.scene_id);
    return ids;
  }, [lesson.scenes, lesson.followups, jobs]);

  const current = jobs.filter((j) => j.status === "RUNNING");
  const first = ts(jobs[0]?.started_at);
  const lastEnd = Math.max(0, ...jobs.map((j) => (j.status === "RUNNING" ? now : ts(j.finished_at) ?? 0)));
  const total = first ? (lastEnd - first) / 1000 : 0;
  const pick = (stages: string[], scene?: string) =>
    jobs.filter((j) => stages.includes(j.stage) && (scene === undefined ? !j.scene_id : j.scene_id === scene));

  return (
    <div className="card p-4">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="label">Etapy generowania</h2>
        {total > 0 && <span className="font-mono text-xs text-slate-500">łącznie {fmt(total)}</span>}
        {current.length > 0 && (
          <span className="text-xs text-lens-700">
            Teraz:{" "}
            {current
              .map((j) => `${j.stage}${j.scene_id ? ` (${j.scene_id})` : ""} ${fmt(Math.max(0, (now - (ts(j.started_at) ?? now)) / 1000))}`)
              .join(" · ")}
          </span>
        )}
        <button className="btn-ghost ml-auto text-xs" onClick={() => setOpen((v) => !v)}>
          {open ? "Zwiń" : "Rozwiń"}
        </button>
      </div>
      {open && (
        <>
          <div className="mt-3 flex flex-wrap items-stretch gap-2">
            {GLOBAL.map((g, i) => (
              <div key={g.stage} className="flex items-center gap-2">
                {i > 0 && <span className="text-slate-300">→</span>}
                <Chip label={g.label} cell={summarise(pick([g.stage]), now)} />
              </div>
            ))}
          </div>
          {sceneIds.length > 0 && (
            <div className="mt-3 overflow-x-auto">
              <table className="text-xs">
                <thead>
                  <tr className="text-left text-slate-500">
                    <th className="pr-3 font-medium">Scena</th>
                    {SCENE.map((c) => (
                      <th key={c.key} className="px-1 font-medium">
                        {c.label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {sceneIds.map((sid) => {
                    const title = lesson.scenes.find((s) => s.scene_id === sid)?.title;
                    return (
                      <tr key={sid}>
                        <td className="max-w-[180px] truncate pr-3 text-slate-600" title={title}>
                          {sid}
                          {title ? ` · ${title}` : ""}
                        </td>
                        {SCENE.map((c) => {
                          const cell = summarise(pick(c.stages, sid), now);
                          return (
                            <td key={c.key} className="p-1">
                              <Chip label={c.label} cell={cell} title={cell.model ?? undefined} />
                            </td>
                          );
                        })}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <span className="text-slate-300">→</span>
            <Chip label="Sklejanie filmu" cell={summarise(pick(["concat"]), now)} />
          </div>
          {lesson.followups.length > 0 && (
            <div className="mt-4 overflow-x-auto">
              <h3 className="label mb-1">Pytania (filmiki z odpowiedziami)</h3>
              <table className="text-xs">
                <thead>
                  <tr className="text-left text-slate-500">
                    <th className="pr-3 font-medium">Pytanie</th>
                    {FOLLOWUP.map((c) => (
                      <th key={c.key} className="px-1 font-medium">
                        {c.label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {lesson.followups.map((f) => (
                    <tr key={f.scene_id}>
                      <td className="max-w-[220px] truncate pr-3 text-slate-600" title={f.question ?? undefined}>
                        {f.question || f.scene_id}
                      </td>
                      {FOLLOWUP.map((c) => {
                        const cell = summarise(pick(c.stages, f.scene_id), now);
                        return (
                          <td key={c.key} className="p-1">
                            <Chip label={c.label} cell={cell} title={cell.model ?? undefined} />
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {lesson.current_stage && <p className="mt-2 text-xs text-slate-500">Status lekcji: {lesson.status} · {lesson.current_stage}</p>}
        </>
      )}
    </div>
  );
}
