import { getHighRiskCoins, getLatestCoins, getTopOpportunities } from "@/lib/api";
import CoinTable from "@/components/CoinTable";
import AutoRefresh from "@/components/AutoRefresh";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const [topOpportunities, latestCoins, highRiskCoins] = await Promise.all([
    getTopOpportunities(20).catch(() => []),
    getLatestCoins(15).catch(() => []),
    getHighRiskCoins(10).catch(() => []),
  ]);

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
      <AutoRefresh intervalSeconds={30} />
      <section className="lg:col-span-2 space-y-8">
        <PanelHeader
          eyebrow="Ranked by overall_score · live, updates every 30s"
          title="Top 20 Opportunities"
          description="Liquidity + trend momentum, net of risk penalty."
        />
        <CoinTable
          coins={topOpportunities}
          emptyLabel="No scored coins yet — trigger a discovery + scoring cycle to populate this."
        />

        <PanelHeader
          eyebrow="Newest first"
          title="Latest Coins"
          description="Freshly discovered across Solana, Ethereum, and Base."
        />
        <CoinTable coins={latestCoins} emptyLabel="No coins discovered yet." />
      </section>

      <aside className="space-y-4">
        <PanelHeader
          eyebrow="Ranked by risk_score"
          title="High Risk Coins"
          description="Mint/freeze authority, holder concentration, unlocked LP."
        />
        <CoinTable coins={highRiskCoins} emptyLabel="No risk data yet." variant="risk" />
      </aside>
    </div>
  );
}

function PanelHeader({
  eyebrow,
  title,
  description,
}: {
  eyebrow: string;
  title: string;
  description: string;
}) {
  return (
    <div className="flex items-baseline justify-between border-b border-hairline pb-2">
      <div>
        <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-amber">{eyebrow}</p>
        <h2 className="font-display text-xl font-bold text-ink">{title}</h2>
      </div>
      <p className="hidden sm:block max-w-[220px] text-right text-xs text-ink-muted">
        {description}
      </p>
    </div>
  );
}
