"use client";

import { useEffect, useState } from "react";
import { getTopOpportunities } from "@/lib/api";
import { Coin } from "@/types/coin";
import { formatPercent, formatScore } from "@/lib/format";

export default function TickerTape() {
  const [coins, setCoins] = useState<Coin[]>([]);

  useEffect(() => {
    let mounted = true;
    function load() {
      getTopOpportunities(20)
        .then((data) => mounted && setCoins(data))
        .catch(() => mounted && setCoins([]));
    }
    load();
    const interval = setInterval(load, 60_000);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, []);

  if (coins.length === 0) {
    return (
      <div className="border-b border-hairline bg-panel py-1.5">
        <p className="text-center font-mono text-[11px] text-ink-faint">
          waiting for scored coins…
        </p>
      </div>
    );
  }

  const items = [...coins, ...coins]; // duplicate for seamless loop

  return (
    <div className="border-b border-hairline bg-panel overflow-hidden">
      <div className="flex w-max animate-ticker py-1.5 hover:[animation-play-state:paused]">
        {items.map((coin, idx) => {
          const change = coin.price_change_24h ?? 0;
          const changeColor = change >= 0 ? "text-mint" : "text-alert";
          return (
            <div
              key={`${coin.id}-${idx}`}
              className="flex items-center gap-2 whitespace-nowrap border-r border-hairline px-4 font-mono text-xs"
            >
              <span className="text-ink">{coin.symbol || "—"}</span>
              <span className="text-amber">{formatScore(coin.score?.overall_score)}</span>
              <span className={changeColor}>{formatPercent(coin.price_change_24h)}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
