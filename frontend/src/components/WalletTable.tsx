import Link from "next/link";
import { Wallet } from "@/types/coin";
import { chainLabel, formatDuration, formatPercent, truncateAddress } from "@/lib/format";

export default function WalletTable({ wallets, emptyLabel }: { wallets: Wallet[]; emptyLabel: string }) {
  if (wallets.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-hairline bg-panel/50 px-4 py-8 text-center">
        <p className="font-mono text-xs text-ink-faint">{emptyLabel}</p>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-hairline">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-hairline bg-panel-raised font-mono text-[11px] uppercase tracking-wider text-ink-muted">
            <th className="px-3 py-2 font-medium" title="The wallet's on-chain address. Hover a row to see the full address.">
              Wallet
            </th>
            <th className="px-3 py-2 font-medium">Chain</th>
            <th
              className="px-3 py-2 font-medium text-right cursor-help"
              title="0-100 blended score: 40% win rate + 30% ROI magnitude + 20% how often this wallet enters early + 10% a sample-size confidence term (so one lucky trade can't outrank a long, proven track record). Computed across every EVM coin this platform has seen the wallet trade, not just one."
            >
              Reputation
            </th>
            <th
              className="px-3 py-2 font-medium text-right cursor-help"
              title="Share of this wallet's tracked positions that closed in profit."
            >
              Win Rate
            </th>
            <th
              className="px-3 py-2 font-medium text-right cursor-help"
              title="Average return across this wallet's tracked positions, weighted equally per position."
            >
              Avg ROI
            </th>
            <th
              className="px-3 py-2 font-medium text-right cursor-help"
              title="How long this wallet typically holds a position before its balance changes significantly."
            >
              Avg Hold
            </th>
            <th
              className="px-3 py-2 font-medium text-right cursor-help"
              title="Every coin this wallet has transacted with, tracked by this platform. Bright = latest transaction was a buy (likely still holding). Dim/struck = latest transaction was a sell or transfer out (likely no longer held) - a proxy, not an exact balance (see note above)."
            >
              Held Coins
            </th>
            <th
              className="px-3 py-2 font-medium text-right cursor-help"
              title="How many coins (tracked by this platform) this wallet has taken a position in - a low count means the reputation score is based on a thinner sample, and is weighted down accordingly (see Reputation)."
            >
              Positions
            </th>
          </tr>
        </thead>
        <tbody>
          {wallets.map((w) => {
            const roi = w.avg_roi_pct ?? 0;
            const rep = w.reputation_score ?? 0;
            const repColor = rep >= 65 ? "text-mint" : rep >= 35 ? "text-amber" : "text-ink-muted";
            return (
              <tr key={w.id} className="border-b border-hairline/60 last:border-0 hover:bg-panel-raised transition-colors">
                <td className="px-3 py-2 font-mono text-ink" title={w.address}>
                  {truncateAddress(w.address, 5)}
                </td>
                <td className="px-3 py-2">
                  <span className="rounded border border-hairline px-1.5 py-0.5 font-mono text-[10px] uppercase text-ink-muted">
                    {chainLabel(w.chain)}
                  </span>
                </td>
                <td className={`px-3 py-2 text-right font-mono font-medium ${repColor}`}>
                  {w.reputation_score === null ? "—" : w.reputation_score.toFixed(0)}
                </td>
                <td className="px-3 py-2 text-right font-mono text-ink-muted">
                  {w.win_rate === null ? "—" : `${(w.win_rate * 100).toFixed(0)}%`}
                </td>
                <td className={`px-3 py-2 text-right font-mono ${roi >= 0 ? "text-mint" : "text-alert"}`}>
                  {formatPercent(w.avg_roi_pct)}
                </td>
                <td className="px-3 py-2 text-right font-mono text-xs text-ink-muted">
                  {formatDuration(w.avg_hold_time_seconds)}
                </td>
                <td className="px-3 py-2 text-right">
                  <div className="flex flex-wrap justify-end gap-1 max-w-[220px] ml-auto">
                    {(w.held_coins ?? []).length === 0 ? (
                      <span className="font-mono text-xs text-ink-faint">—</span>
                    ) : (
                      (w.held_coins ?? []).map((hc) => (
                        <Link
                          key={hc.coin_id}
                          href={`/coins/${hc.coin_id}`}
                          title={hc.still_holding ? "Likely still holding" : "Likely sold / moved on"}
                          className={`rounded border px-1.5 py-0.5 font-mono text-[10px] transition-colors ${
                            hc.still_holding
                              ? "border-mint/40 text-mint hover:border-mint"
                              : "border-hairline text-ink-faint line-through decoration-ink-faint/60 hover:border-ink-muted"
                          }`}
                        >
                          {hc.symbol || "?"}
                        </Link>
                      ))
                    )}
                  </div>
                </td>
                <td className="px-3 py-2 text-right font-mono text-xs text-ink-muted">{w.total_positions}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
