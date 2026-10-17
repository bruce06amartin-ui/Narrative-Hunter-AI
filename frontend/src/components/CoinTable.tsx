import Link from "next/link";
import { Coin } from "@/types/coin";
import { chainLabel, formatPercent, formatScore, formatUsd, timeAgo } from "@/lib/format";

export default function CoinTable({
  coins,
  emptyLabel,
  variant = "overall",
}: {
  coins: Coin[];
  emptyLabel: string;
  variant?: "overall" | "risk";
}) {
  if (coins.length === 0) {
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
            <th className="px-3 py-2 font-medium">Coin</th>
            <th className="px-3 py-2 font-medium">Chain</th>
            <th className="px-3 py-2 font-medium text-right">Liquidity</th>
            <th className="px-3 py-2 font-medium text-right">24h</th>
            <th className="px-3 py-2 font-medium text-right">
              {variant === "risk" ? "Risk" : "Score"}
            </th>
            <th className="px-3 py-2 font-medium text-right">Age</th>
          </tr>
        </thead>
        <tbody>
          {coins.map((coin) => {
            const change = coin.price_change_24h ?? 0;
            const scoreValue =
              variant === "risk" ? coin.score?.risk_score : coin.score?.overall_score;
            const scoreColor =
              variant === "risk"
                ? (scoreValue ?? 0) >= 60
                  ? "text-alert"
                  : (scoreValue ?? 0) >= 30
                  ? "text-amber"
                  : "text-ink-muted"
                : "text-amber";
            return (
              <tr
                key={coin.id}
                className="border-b border-hairline/60 last:border-0 hover:bg-panel-raised transition-colors"
              >
                <td className="px-3 py-2">
                  <Link href={`/coins/${coin.id}`} className="flex flex-col group">
                    <span className="font-mono text-ink group-hover:text-amber transition-colors">
                      {coin.symbol || "—"}
                    </span>
                    <span className="text-xs text-ink-muted truncate max-w-[160px]">{coin.name}</span>
                  </Link>
                </td>
                <td className="px-3 py-2">
                  <span className="rounded border border-hairline px-1.5 py-0.5 font-mono text-[10px] uppercase text-ink-muted">
                    {chainLabel(coin.chain)}
                  </span>
                </td>
                <td className="px-3 py-2 text-right font-mono text-ink">
                  {coin.score?.liquidity_score === null && (coin.liquidity_usd ?? 0) > 0 ? (
                    <span
                      className="inline-flex items-center gap-1 text-alert"
                      title="Claimed liquidity failed a manipulation sanity check (implausible relative to trading volume) - excluded from scoring, not trusted."
                    >
                      <span aria-hidden="true">⚠</span>
                      <span className="line-through decoration-alert/60">{formatUsd(coin.liquidity_usd)}</span>
                    </span>
                  ) : (
                    formatUsd(coin.liquidity_usd)
                  )}
                </td>
                <td
                  className={`px-3 py-2 text-right font-mono ${
                    change >= 0 ? "text-mint" : "text-alert"
                  }`}
                >
                  {formatPercent(coin.price_change_24h)}
                </td>
                <td className="px-3 py-2 text-right font-mono">
                  <span className={`font-medium ${scoreColor}`}>{formatScore(scoreValue)}</span>
                  {variant === "overall" && coin.score?.confidence != null && (
                    <span
                      className="ml-1.5 text-[10px] text-ink-faint"
                      title="Confidence: how much of the full signal set (liquidity, trend, wallet, narrative, community) was actually confirmed - a high score built on low confidence is pulled toward neutral, but still worth reading with caution."
                    >
                      {Math.round(coin.score.confidence * 100)}%
                    </span>
                  )}
                </td>
                <td className="px-3 py-2 text-right font-mono text-xs text-ink-muted">
                  {timeAgo(coin.launch_time)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
