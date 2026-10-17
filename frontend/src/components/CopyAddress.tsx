"use client";

import { useState } from "react";
import { truncateAddress } from "@/lib/format";

export default function CopyAddress({ address, label }: { address: string; label?: string }) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(address);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // clipboard API unavailable — silently ignore, address is still visible
    }
  }

  return (
    <button
      onClick={handleCopy}
      className="group inline-flex items-center gap-1.5 rounded border border-hairline bg-panel px-2 py-1 font-mono text-xs text-ink-muted hover:border-amber/40 hover:text-amber transition-colors"
      title={address}
    >
      {label && <span className="text-ink-faint">{label}:</span>}
      {truncateAddress(address, 6)}
      <span className="text-[10px]">{copied ? "copied" : "copy"}</span>
    </button>
  );
}
