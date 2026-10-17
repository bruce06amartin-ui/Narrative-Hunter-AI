import { RiskFlag } from "@/types/coin";
import { severityColor } from "@/lib/format";

export default function RiskFlagsList({ flags }: { flags: RiskFlag[] }) {
  if (flags.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-hairline bg-panel/50 px-4 py-6 text-center">
        <p className="font-mono text-xs text-ink-faint">
          No risk flags detected in available checks — no risk data run yet, or the token is clean.
        </p>
      </div>
    );
  }

  return (
    <ul className="space-y-2">
      {flags.map((flag) => (
        <li
          key={flag.flag_type}
          className={`flex items-start justify-between gap-3 rounded-md border px-3 py-2 ${severityColor(
            flag.severity
          )}`}
        >
          <div>
            <p className="font-mono text-xs uppercase tracking-wide">
              {flag.flag_type.replace(/_/g, " ")}
            </p>
            <p className="mt-0.5 text-xs opacity-80">{flag.description}</p>
          </div>
          <span className="shrink-0 font-mono text-xs font-semibold">+{flag.points.toFixed(0)}</span>
        </li>
      ))}
    </ul>
  );
}
