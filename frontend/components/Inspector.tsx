"use client";

import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import type { Job, Lesson, Scene, Timings } from "@/types";

const TABS = ["ProblemIR", "ScopeIR", "SolutionIR", "LessonIR", "Scene", "Narration", "VisualPlan", "AnimationPlan", "Manim", "Validation", "Jobs"] as const;
type Tab = (typeof TABS)[number];

function Json({ value }: { value: unknown }) {
  return (
    <pre className="max-h-[480px] overflow-auto rounded-lg bg-slate-900 p-3 text-xs leading-relaxed text-slate-100">
      {value === undefined || value === null ? "— not generated yet —" : JSON.stringify(value, null, 2)}
    </pre>
  );
}

export function Inspector({ lesson, scene }: { lesson: Lesson; scene: Scene | null }) {
  const [tab, setTab] = useState<Tab>("SolutionIR");
  const [jobs, setJobs] = useState<Job[]>([]);
  const [timings, setTimings] = useState<Timings | null>(null);

  useEffect(() => {
    if (tab === "Jobs") {
      api.jobs(lesson.id).then(setJobs).catch(() => setJobs([]));
      api.timings(lesson.id).then(setTimings).catch(() => setTimings(null));
    }
  }, [tab, lesson.id, lesson.status]);

  let body: React.ReactNode;
  switch (tab) {
    case "ProblemIR":
      body = <Json value={lesson.problem_ir} />;
      break;
    case "ScopeIR":
      body = <Json value={lesson.scope_ir} />;
      break;
    case "SolutionIR":
      body = <Json value={lesson.solution_ir} />;
      break;
    case "LessonIR":
      body = <Json value={lesson.lesson_ir} />;
      break;
    case "Scene":
      body = <Json value={scene?.scene_ir} />;
      break;
    case "Narration":
      body = <Json value={scene?.narration} />;
      break;
    case "VisualPlan":
      body = (
        <div className="space-y-2">
          {scene?.visual_meta && (
            <div className="flex flex-wrap items-center gap-1 text-xs text-slate-600">
              <span className="font-semibold">Retrieved templates:</span>
              {(scene.visual_meta.retrieved_templates ?? []).map((t) => (
                <span key={t} className={`chip ${t === scene.visual_plan?.template ? "!bg-lens-600 !text-white" : ""}`}>
                  {t}
                </span>
              ))}
              <span className="ml-2">
                plan {scene.visual_meta.valid ? "✓ valid" : "✗ invalid"} · code{" "}
                {scene.visual_meta.code_source === "compiled" ? "compiled by the visual engine" : "written by Gemini (fallback)"}
              </span>
            </div>
          )}
          <Json value={scene?.visual_plan} />
        </div>
      );
      break;
    case "AnimationPlan":
      body = scene?.animation_plan ? (
        <table className="w-full text-xs">
          <thead className="text-left text-slate-500">
            <tr>
              <th className="py-1">Beat</th>
              <th>Primitive</th>
              <th>Targets</th>
              <th>s</th>
            </tr>
          </thead>
          <tbody>
            {scene.animation_plan.steps.map((st, k) => (
              <tr key={k} className="border-t border-slate-100">
                <td className="py-1 font-mono text-slate-500">{st.beat}</td>
                <td className="font-medium">{st.primitive}</td>
                <td className="font-mono">{st.targets.join(", ")}</td>
                <td>{st.run_time}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="text-sm text-slate-400">No animation plan (scene code was written by Gemini as a fallback).</p>
      );
      break;
    case "Manim":
      body = (
        <div className="space-y-2">
          <pre className="max-h-[480px] overflow-auto rounded-lg bg-slate-900 p-3 text-xs text-slate-100">
            {scene?.manim_code?.code ?? "— not generated yet —"}
          </pre>
          {scene?.render_stderr && (
            <details>
              <summary className="cursor-pointer text-xs text-slate-500">Render stderr</summary>
              <pre className="max-h-64 overflow-auto rounded bg-slate-100 p-2 text-xs">{scene.render_stderr}</pre>
            </details>
          )}
        </div>
      );
      break;
    case "Validation":
      body = (
        <div className="space-y-2">
          {lesson.validations.length === 0 && <p className="text-sm text-slate-400">No validations yet.</p>}
          {lesson.validations.map((v) => (
            <div key={`${v.validator}:${v.target}`} className="rounded-lg border border-slate-200 p-2 text-xs">
              <div className="flex items-center gap-2">
                <span className={v.passed ? "text-emerald-600" : "text-red-600"}>{v.passed ? "✓" : "✗"}</span>
                <span className="font-semibold">{v.validator}</span>
                <span className="text-slate-500">{v.target}</span>
              </div>
              {v.issues.map((i, k) => (
                <p key={k} className={i.severity === "error" ? "text-red-600" : "text-amber-600"}>
                  [{i.code}] {i.message} {i.location ? `@ ${i.location}` : ""}
                </p>
              ))}
              {v.validator === "math" && Object.keys(v.details).length > 0 && (
                <pre className="mt-1 overflow-auto rounded bg-slate-50 p-2">{JSON.stringify(v.details, null, 2)}</pre>
              )}
            </div>
          ))}
        </div>
      );
      break;
    case "Jobs":
      body = (
        <div className="space-y-3">
          {timings && timings.total_s > 0 && (
            <div className="text-xs">
              <div className="mb-1 font-semibold">Where the time went · {timings.total_s.toFixed(1)} s</div>
              {Object.entries(timings.phases).map(([name, sec]) => (
                <div key={name} className="flex items-center gap-2">
                  <span className="w-48 shrink-0 font-mono text-slate-600">{name}</span>
                  <div className="h-2 rounded bg-lens-500" style={{ width: `${Math.max(2, (300 * sec) / timings.total_s)}px` }} />
                  <span className="text-slate-500">{sec.toFixed(1)} s</span>
                </div>
              ))}
            </div>
          )}
        <table className="w-full text-xs">
          <thead className="text-left text-slate-500">
            <tr>
              <th className="py-1">Stage</th>
              <th>Scene</th>
              <th>Status</th>
              <th>Model</th>
              <th>Prompt</th>
              <th>Tries</th>
              <th>ms</th>
            </tr>
          </thead>
          <tbody>
            {jobs.map((j, i) => (
              <tr key={i} className="border-t border-slate-100" title={j.error ?? ""}>
                <td className="py-1 font-medium">{j.stage}</td>
                <td>{j.scene_id ?? ""}</td>
                <td className={j.status === "FAILED" ? "text-red-600" : "text-emerald-600"}>{j.status}</td>
                <td>{j.model}</td>
                <td>{j.prompt_name ? `${j.prompt_name}@${j.prompt_version}` : ""}</td>
                <td>{j.attempts}</td>
                <td>{j.duration_ms ?? ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      );
      break;
  }

  return (
    <section className="card p-4">
      <h2 className="label">Inspect the generated structure</h2>
      <div className="mt-2 flex flex-wrap gap-1">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`rounded-md px-2 py-1 text-xs font-medium ${tab === t ? "bg-ink text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"}`}
          >
            {t}
          </button>
        ))}
      </div>
      <div className="mt-3">{body}</div>
    </section>
  );
}
