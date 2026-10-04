"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { AskTutor } from "@/components/AskTutor";
import { Inspector } from "@/components/Inspector";
import { PipelineProgress } from "@/components/PipelineProgress";
import { SceneInfo } from "@/components/SceneInfo";
import { SceneList } from "@/components/SceneList";
import { StatusBadge } from "@/components/StatusBadge";
import { api, BUSY } from "@/lib/api";
import { QUALITIES } from "@/lib/quality";
import type { Lesson, Scene } from "@/types";

function followupInProgress(f: Scene): boolean {
  return f.status !== "FAILED" && f.render_status !== "COMPLETED" && f.render_status !== "FAILED";
}

export default function LessonPage({ params }: { params: Promise<{ id: string }> }) {
  const [id, setId] = useState<string | null>(null);
  const [lesson, setLesson] = useState<Lesson | null>(null);
  const [sceneId, setSceneId] = useState<string | null>(null);
  const [fullLesson, setFullLesson] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [artifact, setArtifact] = useState("manim");
  const [quality, setQuality] = useState<string | null>(null);

  useEffect(() => {
    params.then((p) => setId(p.id));
  }, [params]);

  const refresh = useCallback(async (): Promise<Lesson | null> => {
    if (!id) return null;
    try {
      const l = await api.getLesson(id);
      setLesson(l);
      setError(null);
      setSceneId((cur) => cur ?? l.scenes[0]?.scene_id ?? null);
      return l;
    } catch (e) {
      setError((e as Error).message);
      return null;
    }
  }, [id]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const busy = lesson ? BUSY.has(lesson.status) : true;
  const followupsBusy = lesson?.followups.some(followupInProgress) ?? false;
  useEffect(() => {
    if (!busy && !followupsBusy) return;
    const t = setInterval(refresh, 2000);
    return () => clearInterval(t);
  }, [busy, followupsBusy, refresh]);

  const scene = useMemo(
    () => [...(lesson?.scenes ?? []), ...(lesson?.followups ?? [])].find((s) => s.scene_id === sceneId) ?? null,
    [lesson, sceneId],
  );
  const isFollowup = scene?.kind === "followup";
  // Questions are always asked about a main lesson scene.
  const askScene = useMemo(
    () => (isFollowup ? lesson?.scenes.find((s) => s.scene_id === scene?.parent_scene_id) ?? null : scene),
    [isFollowup, lesson, scene],
  );
  const videoUrl = fullLesson ? lesson?.video_url : scene?.video_url;

  async function regenerate(art: string, instruction?: string) {
    if (!id || !scene) return;
    try {
      await api.regenerate(id, scene.scene_id, art, instruction);
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  if (!lesson) {
    return <p className="text-slate-500">{error ?? "Loading lesson…"}</p>;
  }

  const mainIndex = lesson.scenes.findIndex((s) => s.scene_id === (askScene?.scene_id ?? sceneId));
  const placeholder =
    scene?.status === "FAILED" || scene?.render_status === "FAILED"
      ? `Generation failed for this ${isFollowup ? "answer" : "scene"}. ${scene?.error?.split("\n")[0] ?? ""}`
      : isFollowup
        ? "Generating your video answer: planning → narration → voice → animation → render…"
        : busy
          ? "The animation is being generated and rendered…"
          : "No video for this scene yet.";

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-xl font-bold">{lesson.lesson_ir?.title ?? "Generating lesson…"}</h1>
          <p className="mt-1 max-w-4xl whitespace-pre-line text-sm text-slate-600">{lesson.problem_text}</p>
        </div>
        <div className="flex items-center gap-2">
          <StatusBadge status={lesson.status} />
          {lesson.status === "FAILED" && (
            <button className="btn-ghost" onClick={() => id && api.retry(id).then(refresh)}>
              Retry (reuses valid stages)
            </button>
          )}
          {(lesson.status === "READY" || lesson.status === "COMPLETED") && (
            <>
              <select
                className="rounded-lg border border-slate-300 px-2 py-1 text-sm"
                title="Video quality"
                value={quality ?? lesson.render_quality ?? "l"}
                onChange={(e) => setQuality(e.target.value)}
              >
                {QUALITIES.map((q) => (
                  <option key={q.value} value={q.value}>
                    {q.label}
                  </option>
                ))}
              </select>
              <button
                className="btn-ghost"
                onClick={() => id && api.render(id, undefined, quality ?? lesson.render_quality ?? undefined).then(refresh)}
              >
                Re-render
              </button>
            </>
          )}
        </div>
      </div>

      <PipelineProgress lesson={lesson} />
      {lesson.error && (
        <div className="whitespace-pre-wrap rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{lesson.error}</div>
      )}
      {error && <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>}

      <div className="grid gap-4 lg:grid-cols-[260px_minmax(0,1fr)_340px]">
        <SceneList
          scenes={lesson.scenes}
          followups={lesson.followups}
          current={sceneId}
          onSelect={(s) => {
            setSceneId(s);
            setFullLesson(false);
          }}
        />

        <div className="space-y-3">
          {isFollowup && scene && (
            <div className="card border-lens-500 p-3">
              <div className="label">Your question</div>
              <p className="mt-1 font-medium">{scene.question}</p>
              {scene.followup?.answer_summary && <p className="mt-1 text-sm text-slate-600">{scene.followup.answer_summary}</p>}
            </div>
          )}

          <div className="card overflow-hidden">
            <div className="aspect-video bg-ink">
              {videoUrl ? (
                <video key={videoUrl} src={videoUrl} controls autoPlay className="h-full w-full" />
              ) : (
                <div className="flex h-full items-center justify-center p-6 text-center text-sm text-slate-300">{placeholder}</div>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-2 border-t border-slate-200 p-2">
              <button
                className="btn-ghost"
                disabled={mainIndex <= 0}
                onClick={() => setSceneId(lesson.scenes[mainIndex - 1].scene_id)}
              >
                ← Prev
              </button>
              <button
                className="btn-ghost"
                disabled={mainIndex < 0 || mainIndex >= lesson.scenes.length - 1}
                onClick={() => setSceneId(lesson.scenes[mainIndex + 1].scene_id)}
              >
                Next →
              </button>
              {isFollowup && askScene && (
                <button className="btn-ghost" onClick={() => setSceneId(askScene.scene_id)}>
                  ↩ Back to “{askScene.title}”
                </button>
              )}
              {lesson.video_url && !isFollowup && (
                <>
                  <button className="btn-ghost" onClick={() => setFullLesson((v) => !v)}>
                    {fullLesson ? "Show current scene" : "Play whole lesson"}
                  </button>
                  <a className="btn-ghost" href={lesson.video_url} download>
                    Download whole lesson
                  </a>
                </>
              )}
              {scene?.video_url && (
                <a className="btn-ghost" href={scene.video_url} download>
                  Download scene
                </a>
              )}
              <div className="ml-auto flex items-center gap-1">
                <select
                  className="rounded-lg border border-slate-300 px-2 py-1 text-sm"
                  value={artifact}
                  onChange={(e) => setArtifact(e.target.value)}
                >
                  <option value="manim">Manim code only</option>
                  <option value="visual">Visual plan + code</option>
                  <option value="narration">Narration + voice + visuals + code</option>
                  <option value="scene">Whole scene</option>
                </select>
                <button
                  className="btn-ghost"
                  disabled={!scene || (isFollowup ? followupInProgress(scene) : busy)}
                  onClick={() => regenerate(artifact)}
                >
                  ↻ Regenerate
                </button>
              </div>
            </div>
          </div>

          {scene?.narration && (
            <div className="card p-4">
              <h2 className="label">
                Narration {scene.voiceover ? `· 🔊 voiceover (${scene.voiceover.voice})` : "· (no voiceover)"}
              </h2>
              <ol className="mt-2 space-y-1 text-sm">
                {scene.narration.segments.map((s) => (
                  <li key={s.id} className="flex gap-2">
                    <span className="mt-0.5 shrink-0 rounded bg-slate-100 px-1.5 font-mono text-[10px] text-slate-500">
                      {s.visual_event}
                    </span>
                    <span>{s.text}</span>
                  </li>
                ))}
              </ol>
            </div>
          )}
        </div>

        <SceneInfo lesson={lesson} scene={scene} />
      </div>

      {id && (
        <AskTutor
          lessonId={id}
          scene={askScene}
          followups={lesson.followups}
          onCreated={async (newId) => {
            const latest = await refresh();
            if (latest?.followups.some((followup) => followup.scene_id === newId)) {
              setSceneId(newId);
            }
            setFullLesson(false);
          }}
          onSelect={(s) => setSceneId(s)}
          disabled={!lesson.lesson_ir || !askScene?.scene_ir}
        />
      )}

      <Inspector lesson={lesson} scene={scene} />
    </div>
  );
}
