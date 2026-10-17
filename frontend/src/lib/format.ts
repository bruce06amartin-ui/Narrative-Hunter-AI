export function formatUsd(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(2)}M`;
  if (value >= 1_000) return `$${(value / 1_000).toFixed(1)}K`;
  if (value < 0.01 && value > 0) return `$${value.toExponential(2)}`;
  return `$${value.toFixed(2)}`;
}

export function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(1)}%`;
}

export function formatScore(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return value.toFixed(0);
}

export function truncateAddress(address: string, chars = 4): string {
  if (!address || address.length <= chars * 2 + 2) return address;
  return `${address.slice(0, chars)}…${address.slice(-chars)}`;
}

export function timeAgo(iso: string | null): string {
  if (!iso) return "—";
  const diffMs = Date.now() - new Date(iso).getTime();
  const minutes = Math.floor(diffMs / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "—";
  const hours = seconds / 3600;
  if (hours < 1) return `${Math.round(seconds / 60)}m`;
  if (hours < 48) return `${hours.toFixed(1)}h`;
  return `${(hours / 24).toFixed(1)}d`;
}

export function chainLabel(chain: string): string {
  const map: Record<string, string> = { eth: "ETH", ethereum: "ETH", solana: "SOL", base: "BASE" };
  return map[chain.toLowerCase()] || chain.toUpperCase();
}

export function severityColor(severity: string): string {
  switch (severity) {
    case "critical":
      return "text-alert border-alert/40 bg-alert/10";
    case "high":
    case "warning":
      return "text-amber border-amber/40 bg-amber/10";
    case "medium":
    case "info":
      return "text-mint border-mint/30 bg-mint/10";
    default:
      return "text-ink-faint border-hairline bg-panel-raised";
  }
}
