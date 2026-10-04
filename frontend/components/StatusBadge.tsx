const COLORS: Record<string, string> = {
  COMPLETED: "bg-emerald-100 text-emerald-700",
  GENERATED: "bg-emerald-100 text-emerald-700",
  READY: "bg-sky-100 text-sky-700",
  FAILED: "bg-red-100 text-red-700",
  NOT_STARTED: "bg-slate-100 text-slate-500",
};

export function StatusBadge({ status }: { status: string }) {
  const color = COLORS[status] ?? "bg-amber-100 text-amber-700";
  return <span className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-semibold ${color}`}>{status}</span>;
}
