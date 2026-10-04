import { StatusBadge } from "@/components/StatusBadge";
import type { Scene } from "@/types";

export function sceneState(s: Scene): string {
  if (s.status === "FAILED") return "FAILED";
  if (s.render_status !== "NOT_STARTED") return s.render_status;
  return s.status;
}

export function SceneList({
  scenes,
  followups,
  current,
  onSelect,
}: {
  scenes: Scene[];
  followups: Scene[];
  current: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <nav className="card p-3">
      <h2 className="label px-1">Scenes</h2>
      <ol className="mt-2 space-y-1">
        {scenes.length === 0 && <li className="px-1 text-sm text-slate-400">Planning the lesson…</li>}
        {scenes.map((s, i) => (
          <li key={s.scene_id}>
            <button
              onClick={() => onSelect(s.scene_id)}
              className={`w-full rounded-lg p-2 text-left transition ${
                current === s.scene_id ? "bg-lens-50 ring-1 ring-lens-500" : "hover:bg-slate-50"
              }`}
            >
              <div className="flex items-start gap-2">
                <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-slate-200 text-[11px] font-bold">
                  {i + 1}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium">{s.title}</div>
                  <div className="mt-1 flex flex-wrap items-center gap-1">
                    <StatusBadge status={sceneState(s)} />
                    {s.voiceover && <span className="text-[11px] text-slate-400">🔊 voice</span>}
                    {s.regeneration_count > 0 && (
                      <span className="text-[11px] text-slate-400">regenerated ×{s.regeneration_count}</span>
                    )}
                  </div>
                </div>
              </div>
            </button>

            {followups
              .filter((f) => f.parent_scene_id === s.scene_id)
              .map((f) => (
                <button
                  key={f.scene_id}
                  onClick={() => onSelect(f.scene_id)}
                  className={`ml-7 mt-1 block w-[calc(100%-1.75rem)] rounded-lg border-l-2 border-lens-500 p-2 text-left transition ${
                    current === f.scene_id ? "bg-lens-50 ring-1 ring-lens-500" : "hover:bg-slate-50"
                  }`}
                >
                  <div className="truncate text-xs font-medium text-slate-700">❓ {f.question}</div>
                  <div className="mt-1">
                    <StatusBadge status={sceneState(f)} />
                  </div>
                </button>
              ))}
          </li>
        ))}
      </ol>
    </nav>
  );
}
