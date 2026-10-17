import Link from "next/link";
import { getPaperTrades, getPaperTradingSummary } from "@/lib/api";
import { timeAgo, formatUsd } from "@/lib/format";

export const dynamic = "force-dynamic";

function fmtGbp(v: number | null): string {
  if (v === null) return "—";
  const sign = v >= 0 ? "+" : "";
  return `${sign}£${v.toFixed(2)}`;
}

function pnlColor(v: number | null): string {
  if (v === null) return "text-ink-muted";
  return v >= 0 ? "text-mint" : "text-alert";
}

export default async function PaperTradingPage() {
  const [summary, openTrades, closedTrades] = await Promise.all([
    getPaperTradingSummary().catch(() => null),
    getPaperTrades("open", 100).catch(() => []),
    getPaperTrades("closed", 100).catch(() => []),
  ]);

  return (
    <div className="space-y-6">
      <div className="border-b border-hairline pb-2">
        <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-amber">
          Simulated — no real money, no real wallet
        </p>
        <h1 className="font-display text-2xl font-bold text-ink">Paper Trading</h1>
        <p className="mt-1 max-w-2xl text-sm text-ink-muted">
          {summary ? (
            <>
              Entry: overall_score crosses {summary.entry_score_threshold} with risk_score under{" "}
              {summary.risk_gate_max} (or not yet checked). Exit: +{summary.exit_gain_pct}% target,{" "}
              {summary.stop_loss_pct}% stop-loss, or {summary.max_hold_hours}h max hold. This exists to
              test whether the scoring system is actually any good at picking winners before ever
              considering real execution.
            </>
          ) : (
            "This exists to test whether the scoring system is actually any good at picking winners before ever considering real execution."
          )}
        </p>
      </div>

      {summary && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div className="rounded-lg border border-hairline bg-panel px-3 py-3">
            <p className="font-mono text-[10px] uppercase tracking-wide text-ink-muted">Open / Closed</p>
            <p className="mt-1 font-mono text-lg font-semibold text-ink">
              {summary.open_positions} / {summary.closed_positions}
            </p>
          </div>
          <div className="rounded-lg border border-hairline bg-panel px-3 py-3">
            <p className="font-mono text-[10px] uppercase tracking-wide text-ink-muted">Win Rate</p>
            <p className="mt-1 font-mono text-lg font-semibold text-ink">
              {summary.win_rate_pct === null ? "—" : `${summary.win_rate_pct}%`}
            </p>
            <p className="text-[10px] text-ink-faint">
              of closed trades · {summary.closed_by_take_profit} target / {summary.closed_by_stop_loss} stopped /{" "}
              {summary.closed_by_timeout} timed out
            </p>
          </div>
          <div className="rounded-lg border border-hairline bg-panel px-3 py-3">
            <p className="font-mono text-[10px] uppercase tracking-wide text-ink-muted">Realized P&amp;L</p>
            <p className={`mt-1 font-mono text-lg font-semibold ${pnlColor(summary.total_realized_pnl_gbp)}`}>
              {fmtGbp(summary.total_realized_pnl_gbp)}
            </p>
          </div>
          <div className="rounded-lg border border-hairline bg-panel px-3 py-3">
            <p className="font-mono text-[10px] uppercase tracking-wide text-ink-muted">Total (incl. unrealized)</p>
            <p className={`mt-1 font-mono text-lg font-semibold ${pnlColor(summary.total_pnl_gbp)}`}>
              {fmtGbp(summary.total_pnl_gbp)}
            </p>
          </div>
        </div>
      )}

      <section>
        <h2 className="mb-2 font-display text-lg font-bold text-ink">Open Positions</h2>
        {openTrades.length === 0 ? (
          <div className="rounded-lg border border-dashed border-hairline bg-panel/50 px-4 py-8 text-center">
            <p className="font-mono text-xs text-ink-faint">
              No open positions yet — nothing has crossed the entry threshold, or /api/paper-trading/run
              hasn&rsquo;t been triggered.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-hairline">
            <table className="w-full border-collapse">
              <thead className="bg-panel-raised">
                <tr>
                  <th className="px-3 py-2 text-left font-mono text-[10px] uppercase text-ink-muted">Coin</th>
                  <th className="px-3 py-2 text-right font-mono text-[10px] uppercase text-ink-muted">Entry Score</th>
                  <th className="px-3 py-2 text-right font-mono text-[10px] uppercase text-ink-muted">Entry Risk</th>
                  <th className="px-3 py-2 text-right font-mono text-[10px] uppercase text-ink-muted">Entry Price</th>
                  <th className="px-3 py-2 text-right font-mono text-[10px] uppercase text-ink-muted">Opened</th>
                </tr>
              </thead>
              <tbody>
                {openTrades.map((t) => (
                  <tr key={t.id} className="border-t border-hairline/60">
                    <td className="px-3 py-2">
                      <Link href={`/coins/${t.coin_id}`} className="font-mono text-sm hover:underline">
                        {t.symbol}
                      </Link>
                      <span className="ml-2 rounded border border-hairline px-1.5 py-0.5 font-mono text-[10px] uppercase text-ink-muted">
                        {t.chain}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-sm text-amber">
                      {t.entry_overall_score.toFixed(0)}
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-sm text-ink-muted">
                      {t.entry_risk_score === null ? "n/a" : t.entry_risk_score.toFixed(0)}
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-sm">{formatUsd(t.entry_price_usd)}</td>
                    <td className="px-3 py-2 text-right font-mono text-[11px] text-ink-muted">
                      {timeAgo(t.entry_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section>
        <h2 className="mb-2 font-display text-lg font-bold text-ink">Closed Positions</h2>
        {closedTrades.length === 0 ? (
          <div className="rounded-lg border border-dashed border-hairline bg-panel/50 px-4 py-8 text-center">
            <p className="font-mono text-xs text-ink-faint">
              No closed positions yet — a position closes on hitting +{summary?.exit_gain_pct ?? 25}%
              target, {summary?.stop_loss_pct ?? -20}% stop-loss, or a {summary?.max_hold_hours ?? 72}h
              max hold.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-hairline">
            <table className="w-full border-collapse">
              <thead className="bg-panel-raised">
                <tr>
                  <th className="px-3 py-2 text-left font-mono text-[10px] uppercase text-ink-muted">Coin</th>
                  <th className="px-3 py-2 text-right font-mono text-[10px] uppercase text-ink-muted">Entry Score</th>
                  <th className="px-3 py-2 text-right font-mono text-[10px] uppercase text-ink-muted">Gain</th>
                  <th className="px-3 py-2 text-right font-mono text-[10px] uppercase text-ink-muted">P&amp;L</th>
                  <th className="px-3 py-2 text-right font-mono text-[10px] uppercase text-ink-muted">Closed</th>
                </tr>
              </thead>
              <tbody>
                {closedTrades.map((t) => (
                  <tr key={t.id} className="border-t border-hairline/60">
                    <td className="px-3 py-2">
                      <Link href={`/coins/${t.coin_id}`} className="font-mono text-sm hover:underline">
                        {t.symbol}
                      </Link>
                      <span className="ml-2 rounded border border-hairline px-1.5 py-0.5 font-mono text-[10px] uppercase text-ink-muted">
                        {t.chain}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-sm text-amber">
                      {t.entry_overall_score.toFixed(0)}
                    </td>
                    <td className={`px-3 py-2 text-right font-mono text-sm ${pnlColor(t.pnl_pct)}`}>
                      {t.pnl_pct === null ? "—" : `+${t.pnl_pct.toFixed(1)}%`}
                    </td>
                    <td className={`px-3 py-2 text-right font-mono text-sm ${pnlColor(t.pnl_gbp)}`}>
                      {fmtGbp(t.pnl_gbp)}
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-[11px] text-ink-muted">
                      {t.exit_at ? timeAgo(t.exit_at) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
