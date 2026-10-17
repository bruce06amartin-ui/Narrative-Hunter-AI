export default function ScoreBar({
  label,
  value,
  tone = "amber",
  note,
}: {
  label: string;
  value: number | null;
  tone?: "amber" | "mint" | "alert";
  note?: string;
}) {
  const pct = value === null ? 0 : Math.max(0, Math.min(100, value));
  const barColor = { amber: "bg-amber", mint: "bg-mint", alert: "bg-alert" }[tone];
  const textColor = { amber: "text-amber", mint: "text-mint", alert: "text-alert" }[tone];

  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between">
        <span className="font-mono text-xs uppercase tracking-wider text-ink-muted">{label}</span>
        <span className={`font-mono text-sm font-semibold ${textColor}`}>
          {value === null ? "n/a" : value.toFixed(0)}
        </span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-panel-raised">
        {value !== null && (
          <div className={`h-full rounded-full ${barColor}`} style={{ width: `${pct}%` }} />
        )}
      </div>
      {note && <p className="mt-1 text-[11px] text-ink-faint">{note}</p>}
    </div>
  );
}
