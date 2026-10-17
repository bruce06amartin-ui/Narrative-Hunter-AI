"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { searchCoins } from "@/lib/api";
import { Coin } from "@/types/coin";
import { chainLabel } from "@/lib/format";

export default function SearchBar() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Coin[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const router = useRouter();

  useEffect(() => {
    if (query.trim().length < 2) {
      setResults([]);
      return;
    }
    setLoading(true);
    const handle = setTimeout(() => {
      searchCoins(query.trim())
        .then((coins) => setResults(coins))
        .catch(() => setResults([]))
        .finally(() => setLoading(false));
    }, 300);
    return () => clearTimeout(handle);
  }, [query]);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  return (
    <div ref={containerRef} className="relative">
      <input
        type="text"
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        placeholder="Search symbol or name…"
        aria-label="Search coins"
        className="w-full rounded-md border border-hairline bg-panel px-3 py-1.5 font-mono text-sm text-ink placeholder:text-ink-faint focus:border-amber/50 focus:outline-none"
      />
      {open && query.trim().length >= 2 && (
        <div className="absolute left-0 right-0 top-full mt-1 max-h-80 overflow-y-auto rounded-md border border-hairline bg-panel shadow-xl">
          {loading && <div className="px-3 py-2 text-xs text-ink-muted">Searching…</div>}
          {!loading && results.length === 0 && (
            <div className="px-3 py-2 text-xs text-ink-muted">No coins match &ldquo;{query}&rdquo;.</div>
          )}
          {!loading &&
            results.map((coin) => (
              <button
                key={coin.id}
                onClick={() => {
                  setOpen(false);
                  setQuery("");
                  router.push(`/coins/${coin.id}`);
                }}
                className="flex w-full items-center justify-between px-3 py-2 text-left hover:bg-panel-raised transition-colors"
              >
                <span className="flex items-center gap-2">
                  <span className="font-mono text-sm text-ink">{coin.symbol || "—"}</span>
                  <span className="text-xs text-ink-muted truncate max-w-[160px]">{coin.name}</span>
                </span>
                <span className="font-mono text-[10px] uppercase text-ink-faint">{chainLabel(coin.chain)}</span>
              </button>
            ))}
        </div>
      )}
    </div>
  );
}
