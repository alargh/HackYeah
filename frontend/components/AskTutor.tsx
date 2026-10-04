"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { StatusBadge } from "@/components/StatusBadge";
import { sceneState } from "@/components/SceneList";
import { api } from "@/lib/api";
import type { ChatMessage, Scene } from "@/types";

const QUICK = [
  { label: "Dlaczego?", question: "Dlaczego ten krok jest poprawny?" },
  { label: "Prościej", question: "Czy możesz wytłumaczyć ten krok prościej?" },
  { label: "Podpowiedź", question: "Daj mi podpowiedź do tego kroku, bez podawania wyniku." },
];

/** Questions are answered in chat (with the whole lesson as context); a narrated video answer is made on request. */
export function AskTutor({
  lessonId,
  scene,
  followups,
  onCreated,
  onSelect,
  disabled,
}: {
  lessonId: string;
  scene: Scene | null; // the main scene being asked about
  followups: Scene[];
  onCreated: (sceneId: string) => void;
  onSelect: (sceneId: string) => void;
  disabled: boolean;
}) {
  const [question, setQuestion] = useState("");
  const [pending, setPending] = useState(false);
  const [videoPending, setVideoPending] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const end = useRef<HTMLDivElement>(null);

  const load = useCallback(() => {
    api
      .messages(lessonId)
      .then(setMessages)
      .catch(() => undefined);
  }, [lessonId]);
  useEffect(() => {
    load();
  }, [load]);
  useEffect(() => {
    // braces matter: newer Chromium returns a Promise from scrollIntoView, and React would call it as a cleanup
    end.current?.scrollIntoView({ block: "nearest" });
  }, [messages.length, pending]);

  async function send(q: string) {
    if (!scene || !q.trim()) return;
    setPending(true);
    setError(null);
    setMessages((m) => [...m, { role: "user", scene_id: scene.scene_id, content: q.trim(), payload: { kind: "chat" } }]);
    setQuestion("");
    let video = false;
    try {
      const reply = await api.chat(lessonId, scene.scene_id, q.trim());
      // "pokaż…" / anything the tutor says needs a drawing: start the narrated video right away
      video = !!reply?.suggest_video;
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setPending(false);
      load();
    }
    if (video) await makeVideo(q.trim());
  }

  async function makeVideo(q: string) {
    if (!scene) return;
    setVideoPending(q);
    setError(null);
    try {
      const res = await api.ask(lessonId, scene.scene_id, q);
      if (!res?.scene_id) throw new Error("Serwer nie zwrócił identyfikatora odpowiedzi.");
      onCreated(res.scene_id);
      load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setVideoPending(null);
    }
  }

  const thread = messages.filter((m) => scene && m.scene_id === scene.scene_id && m.payload?.kind === "chat");
  const mine = followups.filter((f) => scene && f.parent_scene_id === scene.scene_id);
  const lastUser = [...thread].reverse().find((m) => m.role === "user")?.content;

  return (
    <section className="card p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="label">Zapytaj o ten krok {scene ? `· ${scene.title}` : ""}</h2>
        <div className="flex flex-wrap gap-2">
          {QUICK.map((q) => (
            <button key={q.label} className="btn-ghost" disabled={disabled || pending || !scene} onClick={() => send(q.question)}>
              {q.label}
            </button>
          ))}
        </div>
      </div>
      <p className="mt-1 text-xs text-slate-500">
        Tutor odpowiada w czacie, znając całą lekcję. Jeśli potrzebujesz dokładniejszego wyjaśnienia, zrób z
        odpowiedzi krótki filmik z lektorem.
      </p>

      {thread.length > 0 && (
        <div className="mt-3 max-h-80 space-y-2 overflow-y-auto rounded-lg bg-slate-50 p-3">
          {thread.map((m, i) => (
            <div key={i} className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
              <div
                className={`max-w-[85%] whitespace-pre-wrap rounded-xl px-3 py-2 text-sm ${m.role === "user" ? "bg-lens-600 text-white" : "border border-slate-200 bg-white text-slate-800"
                  }`}
              >
                {m.content}
                {m.role !== "user" && (
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    <button
                      className={m.payload?.suggest_video ? "btn-primary text-xs" : "btn-ghost text-xs"}
                      disabled={disabled || !!videoPending}
                      onClick={() => makeVideo(m.payload?.question || lastUser || m.content)}
                      title={m.payload?.video_reason || "Krótki filmik z animacją i lektorem"}
                    >
                      {videoPending === (m.payload?.question || lastUser) ? "Tworzę filmik…" : "🎬 Wytłumacz na filmiku"}
                    </button>
                    {m.payload?.suggest_video && m.payload.video_reason && (
                      <span className="text-xs text-slate-500">{m.payload.video_reason}</span>
                    )}
                  </div>
                )}
              </div>
            </div>
          ))}
          {pending && <div className="text-xs text-slate-400">Tutor pisze…</div>}
          {videoPending && <div className="text-xs text-slate-400">Tworzę filmik z odpowiedzią — postęp w tabeli „Pytania” powyżej…</div>}
          <div ref={end} />
        </div>
      )}

      <form
        className="mt-3 flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          send(question);
        }}
      >
        <input
          className="flex-1 rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-lens-500 focus:outline-none"
          placeholder="Dlaczego mnożymy przez 2?  ·  A co, gdyby osób było 6?"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          disabled={disabled || !scene}
        />
        <button className="btn-primary" disabled={disabled || pending || !question.trim() || !scene}>
          {pending ? "Wysyłam…" : "Zapytaj"}
        </button>
      </form>
      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}

      {mine.length > 0 && (
        <>
          <h3 className="label mt-4">Filmiki z odpowiedziami</h3>
          <ul className="mt-1 space-y-1">
            {mine.map((f) => (
              <li key={f.scene_id}>
                <button onClick={() => onSelect(f.scene_id)} className="flex w-full items-center gap-2 rounded-lg p-2 text-left hover:bg-slate-50">
                  <StatusBadge status={sceneState(f)} />
                  <span className="truncate text-sm">{f.question}</span>
                  {f.error && <span className="truncate text-xs text-red-600">{f.error.split("\n")[0]}</span>}
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
