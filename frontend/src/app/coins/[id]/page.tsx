import { notFound } from "next/navigation";
import Link from "next/link";
import { getCoin, getCoinHistory, getCoinRiskFlags, getCoinWallets, getCoinNarrative, getCoinCommunity } from "@/lib/api";
import { chainLabel, formatPercent, formatScore, formatUsd, timeAgo } from "@/lib/format";
import ScoreBar from "@/components/ScoreBar";
import RiskFlagsList from "@/components/RiskFlagsList";
import ScoreHistoryChart from "@/components/ScoreHistoryChart";
import CopyAddress from "@/components/CopyAddress";
import WalletTable from "@/components/WalletTable";
import NarrativePanel from "@/components/NarrativePanel";
import CommunityPanel from "@/components/CommunityPanel";

export const dynamic = "force-dynamic";

const EVM_WALLET_CHAINS = ["eth", "ethereum", "base"];

export default async function CoinDetailPage({ params }: { params: { id: string } }) {
  let coin, history, riskFlags;
  try {
    [coin, history, riskFlags] = await Promise.all([
      getCoin(params.id),
      getCoinHistory(params.id),
      getCoinRiskFlags(params.id),
    ]);
  } catch {
    notFound();
  }

  const isEvmChain = EVM_WALLET_CHAINS.includes(coin.chain.toLowerCase());
  const [holdingWallets, narrative, community] = await Promise.all([
    isEvmChain ? getCoinWallets(params.id).catch(() => []) : Promise.resolve([]),
    getCoinNarrative(params.id).catch(() => null),
    getCoinCommunity(params.id).catch(() => null),
  ]);

  const change = coin.price_change_24h ?? 0;

  return (
    <div className="space-y-8">
      <Link href="/" className="font-mono text-xs text-ink-muted hover:text-amber transition-colors">
        ← back to dashboard
      </Link>

      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="font-display text-3xl font-bold text-ink">{coin.symbol || "—"}</h1>
            <span className="rounded border border-hairline px-2 py-0.5 font-mono text-xs uppercase text-ink-muted">
              {chainLabel(coin.chain)}
            </span>
          </div>
          <p className="mt-1 text-ink-muted">{coin.name}</p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <CopyAddress address={coin.contract_address} label="contract" />
            <CopyAddress address={coin.id} label="coin id" />
            <span className="font-mono text-xs text-ink-faint">
              discovered via {coin.source} · {timeAgo(coin.launch_time)}
            </span>
          </div>
        </div>

        <div className="text-right">
          <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-amber">Overall Score</p>
          <p className="font-display text-5xl font-bold text-amber">
            {formatScore(coin.score?.overall_score)}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Stat label="Price" value={formatUsd(coin.price_usd)} />
        <Stat
          label="24h Change"
          value={formatPercent(coin.price_change_24h)}
          tone={change >= 0 ? "mint" : "alert"}
        />
        <Stat label="Liquidity" value={formatUsd(coin.liquidity_usd)} />
        <Stat label="24h Volume" value={formatUsd(coin.volume_24h_usd)} />
      </div>

      <section className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2 space-y-3">
          <h2 className="font-display text-lg font-bold text-ink">Score History</h2>
          <ScoreHistoryChart points={history} />
        </div>

        <div className="space-y-4 rounded-lg border border-hairline bg-panel p-4">
          <h2 className="font-display text-lg font-bold text-ink">Score Breakdown</h2>
          <ScoreBar label="Liquidity" value={coin.score?.liquidity_score ?? null} tone="amber" />
          <ScoreBar label="Trend" value={coin.score?.trend_score ?? null} tone="mint" />
          <ScoreBar
            label="Risk"
            value={coin.score?.risk_score ?? null}
            tone="alert"
            note="Subtracted as a penalty, not part of the same 100% pool as liquidity/trend/wallet."
          />
          <ScoreBar
            label="Wallet"
            value={coin.score?.wallet_score ?? null}
            tone="mint"
            note={
              coin.score?.wallet_source === "evm"
                ? "Mean reputation of wallets holding this coin, based on their track record across every coin tracked here."
                : coin.score?.wallet_source === "solana"
                ? "Current top holders' profit/loss on THIS coin specifically, not a cross-coin track record like the EVM version - so it's naturally correlated with this coin's own price trend, a real but weaker signal."
                : isEvmChain
                ? "Not available yet — needs ETHERSCAN_API_KEY configured."
                : "Not available yet — needs SOLANATRACKER_API_KEY configured."
            }
          />
          <ScoreBar
            label="Narrative"
            value={coin.score?.narrative_score ?? null}
            tone="amber"
            note={
              narrative?.narrative_summary
                ? "See full narrative analysis below."
                : "Needs a social source (Reddit/CryptoPanic/X) + ANTHROPIC_API_KEY configured."
            }
          />
          <ScoreBar
            label="Community"
            value={coin.score?.community_score ?? null}
            tone="mint"
            note={
              community && community.total_posts > 0
                ? "See community health details below."
                : "Needs posts collected by the Narrative Scanner within the lookback window."
            }
          />
          {coin.score?.scoring_notes && (
            <p className="border-t border-hairline pt-3 text-[11px] text-ink-faint">
              {coin.score.scoring_notes}
            </p>
          )}
        </div>
      </section>

      <section className="space-y-3">
        <div className="flex items-baseline justify-between">
          <h2 className="font-display text-lg font-bold text-ink">Narrative Analysis</h2>
          {narrative?.virality_score !== null && narrative?.virality_score !== undefined && (
            <span className="font-mono text-xs text-ink-muted">
              virality score: <span className="text-amber font-semibold">{narrative.virality_score.toFixed(0)}</span>
            </span>
          )}
        </div>
        <NarrativePanel narrative={narrative} />
      </section>

      <section className="space-y-3">
        <h2 className="font-display text-lg font-bold text-ink">Community Health</h2>
        <CommunityPanel community={community} />
      </section>

      <section className="space-y-3">
        <h2 className="font-display text-lg font-bold text-ink">Rug Detection Findings</h2>
        <RiskFlagsList flags={riskFlags} />
      </section>

      {isEvmChain && (
        <section className="space-y-3">
          <div className="flex items-baseline justify-between">
            <h2 className="font-display text-lg font-bold text-ink">Top Holding Wallets</h2>
            <Link href="/wallets" className="font-mono text-xs text-ink-muted hover:text-amber transition-colors">
              full leaderboard →
            </Link>
          </div>
          <WalletTable
            wallets={holdingWallets}
            emptyLabel="No tracked wallets currently holding this coin yet."
          />
        </section>
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: string;
  tone?: "default" | "mint" | "alert";
}) {
  const color = { default: "text-ink", mint: "text-mint", alert: "text-alert" }[tone];
  return (
    <div className="rounded-lg border border-hairline bg-panel px-3 py-2.5">
      <p className="font-mono text-[10px] uppercase tracking-wider text-ink-muted">{label}</p>
      <p className={`mt-0.5 font-mono text-lg font-semibold ${color}`}>{value}</p>
    </div>
  );
}
