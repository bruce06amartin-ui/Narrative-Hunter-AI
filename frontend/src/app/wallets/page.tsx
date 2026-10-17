import { getTopWallets } from "@/lib/api";
import WalletTable from "@/components/WalletTable";

export const dynamic = "force-dynamic";

export default async function WalletsPage() {
  const wallets = await getTopWallets(50).catch(() => []);

  return (
    <div className="space-y-6">
      <div className="border-b border-hairline pb-2">
        <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-amber">
          Module 3 — EVM wallets (eth, base)
        </p>
        <h1 className="font-display text-2xl font-bold text-ink">Wallet Intelligence</h1>
        <p className="mt-1 max-w-2xl text-sm text-ink-muted">
          Every row below is a real wallet address currently holding one or more coins this
          platform tracks. Its <strong className="text-ink">Reputation</strong> score reflects how
          that wallet has performed <em>across every EVM coin we&rsquo;ve seen it trade</em> — not
          just the coin you clicked in from. A wallet showing up here with a high reputation is
          effectively &ldquo;smart money&rdquo; by this platform&rsquo;s own track record, not a
          guess. Requires <code className="text-ink-muted">ETHERSCAN_API_KEY</code> configured
          server-side, and only covers EVM chains — Etherscan has no equivalent on Solana.
        </p>
        <p className="mt-2 max-w-2xl text-sm text-ink-muted">
          Solana wallet intelligence works differently and isn&rsquo;t listed here: instead of a
          browsable wallet directory, it checks a coin&rsquo;s top holders directly and rolls their
          individual profit/loss <em>on that one coin</em> into that coin&rsquo;s own Wallet score —
          visible on the coin&rsquo;s own detail page, not as a standalone wallet entity like the
          EVM ones below.
        </p>
        <p className="mt-2 max-w-2xl text-xs text-ink-faint">
          Worth reading with care: ROI here is a <strong>proxy</strong>, estimated from the nearest
          available price snapshot at the time of a transaction, not the wallet&rsquo;s exact trade
          price (Etherscan gives us transfers, not historical USD pricing). If several different
          wallets bought the same coin within the same snapshot window, they can show identical
          computed ROI even though they&rsquo;re genuinely different wallets — that reflects data
          granularity, not a coincidence or a bug. Many rows also only have 1-2 tracked positions,
          so a 100% win rate can just mean a small sample landed in a coin that&rsquo;s currently
          pumping — the Reputation score already discounts thin samples (see its tooltip above),
          but the raw Win Rate / ROI numbers don&rsquo;t.
        </p>
      </div>

      <WalletTable
        wallets={wallets}
        emptyLabel="No wallet data yet — configure ETHERSCAN_API_KEY and trigger a wallet-intelligence cycle."
      />
    </div>
  );
}
