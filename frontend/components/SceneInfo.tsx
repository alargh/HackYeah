import type { Lesson, Scene } from "@/types";

function Chips({ items, tone = "chip" }: { items: string[]; tone?: string }) {
  if (!items.length) return <span className="text-xs text-slate-400">—</span>;
  return (
    <div className="flex flex-wrap gap-1">
      {items.map((c) => (
        <span key={c} className={tone}>
          {c}
        </span>
      ))}
    </div>
  );
}

export function SceneInfo({ lesson, scene }: { lesson: Lesson; scene: Scene | null }) {
  const ir = scene?.scene_ir;
  const scope = lesson.scope_ir;
  const ledger = lesson.lesson_ir?.concept_ledger.entries ?? [];
  const sceneSymbols = new Set([...(ir?.uses ?? []), ...(ir?.introduces ?? [])]);

  return (
    <aside className="card space-y-4 p-4 text-sm">
      <div>
        <h2 className="label">Current scene</h2>
        <p className="mt-1 font-semibold">{scene?.title ?? "—"}</p>
        {ir && <p className="mt-1 text-slate-600">{ir.learning_goal}</p>}
      </div>

      {ir && (
        <div>
          <h3 className="label">Concepts</h3>
          <div className="mt-1">
            <Chips items={ir.concepts} />
          </div>
        </div>
      )}

      {ir && (
        <div>
          <h3 className="label">Mathematical state</h3>
          {ir.mathematical_state.current_expression && (
            <p className="mt-1 font-mono">
              {ir.mathematical_state.current_expression}
              {ir.mathematical_state.current_value ? ` = ${ir.mathematical_state.current_value}` : ""}
            </p>
          )}
          {!ir.mathematical_state.current_expression && ir.mathematical_state.current_value && (
            <p className="mt-1 font-mono">{ir.mathematical_state.current_value}</p>
          )}
          <ul className="mt-1 list-disc space-y-0.5 pl-4 text-slate-600">
            {ir.mathematical_state.known_facts.map((f) => (
              <li key={f}>{f}</li>
            ))}
          </ul>
        </div>
      )}

      {sceneSymbols.size > 0 && (
        <div>
          <h3 className="label">Notation (concept ledger)</h3>
          <table className="mt-1 w-full text-xs">
            <tbody>
              {ledger
                .filter((e) => sceneSymbols.has(e.symbol))
                .map((e) => (
                  <tr key={e.symbol} className="border-t border-slate-100">
                    <td className="py-1 pr-2 font-mono font-semibold">{e.symbol}</td>
                    <td className="py-1 text-slate-600">
                      {e.meaning}
                      {e.value ? ` (= ${e.value})` : ""}
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      )}

      <div>
        <h3 className="label">Result</h3>
        {lesson.solution_ir ? (
          <div className="mt-1 space-y-1">
            <p className="font-mono">
              {lesson.solution_ir.final_result.expression} = {lesson.solution_ir.final_result.value}
            </p>
            {lesson.math_verified ? (
              <span className="inline-block rounded bg-emerald-100 px-2 py-0.5 text-xs font-semibold text-emerald-700">
                ✓ verified independently by SymPy{lesson.verified_value ? ` (${lesson.verified_value})` : ""}
              </span>
            ) : (
              <span className="inline-block rounded bg-red-100 px-2 py-0.5 text-xs font-semibold text-red-700">
                not verified
              </span>
            )}
          </div>
        ) : (
          <span className="text-xs text-slate-400">—</span>
        )}
      </div>

      <div>
        <h3 className="label">Scope</h3>
        {!scope && <span className="text-xs text-slate-400">—</span>}
        {scope && scope.mode === "open" && <p className="mt-1 text-slate-600">Open (no restriction)</p>}
        {scope && scope.mode === "restricted" && (
          <div className="mt-1 space-y-1">
            {scope.user_scope_text && <p className="italic text-slate-600">“{scope.user_scope_text}”</p>}
            <div>
              <span className="text-xs text-slate-500">Allowed:</span>
              <Chips items={[...scope.allowed_concepts, ...scope.allowed_methods]} />
            </div>
            <div>
              <span className="text-xs text-slate-500">Forbidden:</span>
              <Chips
                items={[...new Set([...scope.forbidden_concepts, ...scope.forbidden_methods])]}
                tone="inline-flex items-center rounded-full bg-red-50 px-2 py-0.5 text-xs font-medium text-red-700"
              />
            </div>
          </div>
        )}
        {lesson.scope_warning && (
          <div className="mt-2 rounded-lg border border-amber-300 bg-amber-50 p-2 text-xs text-amber-800">
            <strong>Scope may be insufficient.</strong> {lesson.scope_warning.explanation}
            {lesson.scope_warning.missing_concepts.length > 0 && (
              <> Missing: {lesson.scope_warning.missing_concepts.join(", ")}</>
            )}
          </div>
        )}
      </div>
    </aside>
  );
}
