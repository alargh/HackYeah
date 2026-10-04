import type { AskResponse, ChatMessage, ChatReply, Job, Lesson, LessonSummary, Timings } from "@/types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    } catch {
      /* ignore */
    }
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => request<{ gemini_configured: boolean; model: string }>("/api/health"),
  createLesson: (problem: string, scope?: string, quality?: string) =>
    request<{ lesson_id: string; status: string }>("/api/lessons", {
      method: "POST",
      body: JSON.stringify({ problem, scope: scope || null, quality: quality || null }),
    }),
  listLessons: () => request<LessonSummary[]>("/api/lessons"),
  getLesson: (id: string) => request<Lesson>(`/api/lessons/${id}`),
  render: (id: string, sceneIds?: string[], quality?: string) =>
    request(`/api/lessons/${id}/render`, {
      method: "POST",
      body: JSON.stringify({ scene_ids: sceneIds ?? null, quality: quality || null }),
    }),
  chat: (id: string, sceneId: string, question: string) =>
    request<ChatReply>(`/api/lessons/${id}/chat`, {
      method: "POST",
      body: JSON.stringify({ scene_id: sceneId, question }),
    }),
  ask: (id: string, sceneId: string, question: string) =>
    request<AskResponse>(`/api/lessons/${id}/ask`, {
      method: "POST",
      body: JSON.stringify({ scene_id: sceneId, question }),
    }),
  regenerate: (id: string, sceneId: string, artifact: string, instruction?: string) =>
    request(`/api/lessons/${id}/scenes/${sceneId}/regenerate`, {
      method: "POST",
      body: JSON.stringify({ artifact, instruction: instruction || null }),
    }),
  retry: (id: string) => request(`/api/lessons/${id}/retry`, { method: "POST" }),
  jobs: (id: string) => request<Job[]>(`/api/lessons/${id}/jobs`),
  timings: (id: string) => request<Timings>(`/api/lessons/${id}/timings`),
  messages: (id: string) => request<ChatMessage[]>(`/api/lessons/${id}/messages`),
};

export const BUSY = new Set(["PENDING", "PLANNING", "GENERATING", "VALIDATING", "RENDERING"]);
