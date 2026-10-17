import Link from "next/link";
import { getAlerts } from "@/lib/api";
import { severityColor, timeAgo } from "@/lib/format";

export const dynamic = "force-dynamic";

const ALERT_TYPE_EXPLANATIONS: Record<string, string> = {
  overall_score_threshold: "Overall score crossed above 70 - the main 'this coin looks like a real opportunity' signal.",
  narrative_score_threshold: "Narrative score crossed above its threshold - AI-analyzed social buzz looks genuinely strong (needs ANTHROPIC_API_KEY).",
  community_score_threshold: "Community score crossed above its threshold - real, organic post activity looks strong (free, no AI needed).",
  risk_score_change: "Risk score moved by 20+ points - could be a new red flag appearing, or (if positive-only mode is on) risk genuinely easing.",
  whale_entry: "A single wallet just made an unusually large buy on this coin.",
  smart_wallet_accumulation: "Multiple wallets with strong track records are accumulating this coin.",
};

export default async function AlertsPage() {
  const alerts = await getAlerts(100).catch(() => []);

  return (
    <div className="space-y-6">
      <div className="border-b border-hairline pb-2">
        <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-amber">
          Module 9 — 6 alert types, all live
        </p>
        <h1 className="font-display text-2xl font-bold text-ink">Alerts</h1>
        <p className="mt-1 max-w-2xl text-sm text-ink-muted">
          Every alert type below is real and currently running: score-threshold crossings, risk
          changes, whale entries, and smart-wallet accumulation. By default, alerts are filtered
          toward positive signals (risk-score <em>increases</em> are suppressed; every other type is
          already a positive signal by construction) and require a minimum liquidity to fire, so
          this feed skips negligible, likely-manipulated, or genuinely dead-trading coins (real
          liquidity with essentially zero current volume). Alerts older than 30 days are
          automatically and permanently deleted to keep this list meaningful — recent history is
          preserved, ancient clutter isn&rsquo;t.
        </p>
      </div>

      {alerts.length === 0 ? (
        <div className="rounded-lg border border-dashed border-hairline bg-panel/50 px-4 py-10 text-center">
          <p className="font-mono text-xs text-ink-faint">
            No alerts yet — trigger discovery → risk → scoring → alerts cycles to populate this.
          </p>
        </div>
      ) : (
        <ul className="space-y-2">
          {alerts.map((alert) => (
            <li
              key={alert.id}
              className={`rounded-md border px-4 py-3 ${severityColor(alert.severity)}`}
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2">
                    <Link
                      href={`/coins/${alert.coin_id}`}
                      className="font-mono text-sm font-semibold hover:underline"
                    >
                      {alert.coin_symbol || "—"}
                    </Link>
                    <span
                      className="font-mono text-[10px] uppercase tracking-wide opacity-70 cursor-help"
                      title={ALERT_TYPE_EXPLANATIONS[alert.alert_type] ?? ""}
                    >
                      {alert.alert_type.replace(/_/g, " ")}
                    </span>
                  </div>
                  <p className="mt-1 text-sm opacity-90">{alert.message}</p>
                  <p className="mt-1 font-mono text-[11px] opacity-60">
                    {alert.delivered
                      ? `delivered via ${alert.channels_delivered}`
                      : "not delivered — no channel configured or all failed"}
                  </p>
                </div>
                <span className="shrink-0 font-mono text-[11px] opacity-70">
                  {timeAgo(alert.created_at)}
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
