import { Coin, HistoricalScorePoint, RiskFlag, Alert, Wallet, Narrative, Community, PaperTrade, PaperTradingSummary } from "@/types/coin";

function getApiUrl(): string {
  if (typeof window === "undefined") {
    // Running server-side (inside the frontend Docker container) - must use
    // the internal Docker network address to reach the api container.
    // "localhost" from inside this container means itself, not the api
    // container - this was a real bug found via live testing.
    return process.env.INTERNAL_API_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  }
  // Running in the browser - must use the externally-exposed address.
  return process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
}

async function apiFetch<T>(path: string, revalidateSeconds = 30): Promise<T> {
  const res = await fetch(`${getApiUrl()}${path}`, {
    next: { revalidate: revalidateSeconds },
  });
  if (!res.ok) {
    throw new Error(`API request failed: ${path} (${res.status})`);
  }
  return res.json();
}

export function getTopOpportunities(limit = 15) {
  return apiFetch<Coin[]>(`/api/coins/top?limit=${limit}`);
}

export function getHighRiskCoins(limit = 10) {
  return apiFetch<Coin[]>(`/api/coins/high-risk?limit=${limit}`);
}

export function getLatestCoins(limit = 15) {
  return apiFetch<Coin[]>(`/api/coins?sort_by=launch_time&limit=${limit}`);
}

export function searchCoins(query: string, limit = 25) {
  return apiFetch<Coin[]>(
    `/api/coins?search=${encodeURIComponent(query)}&limit=${limit}`,
    0
  );
}

export function getCoin(id: string) {
  return apiFetch<Coin>(`/api/coins/${id}`, 10);
}

export function getCoinHistory(id: string, limit = 200) {
  return apiFetch<HistoricalScorePoint[]>(`/api/coins/${id}/history?limit=${limit}`, 10);
}

export function getCoinRiskFlags(id: string) {
  return apiFetch<RiskFlag[]>(`/api/coins/${id}/risk-flags`, 10);
}

export function getAlerts(limit = 50) {
  return apiFetch<Alert[]>(`/api/alerts?limit=${limit}`, 15);
}

export function getCoinAlerts(id: string) {
  return apiFetch<Alert[]>(`/api/coins/${id}/alerts`, 10);
}

export function getCoinWallets(id: string) {
  return apiFetch<Wallet[]>(`/api/coins/${id}/wallets`, 15);
}

export function getTopWallets(limit = 50) {
  return apiFetch<Wallet[]>(`/api/wallets?limit=${limit}`, 30);
}

export function getPaperTrades(status?: "open" | "closed", limit = 100) {
  const statusParam = status ? `status=${status}&` : "";
  return apiFetch<PaperTrade[]>(`/api/paper-trading/trades?${statusParam}limit=${limit}`, 15);
}

export function getPaperTradingSummary() {
  return apiFetch<PaperTradingSummary>(`/api/paper-trading/summary`, 15);
}

export async function getCoinNarrative(id: string): Promise<Narrative | null> {
  const res = await fetch(`${getApiUrl()}/api/coins/${id}/narrative`, { next: { revalidate: 30 } });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`API request failed: narrative (${res.status})`);
  return res.json();
}

export async function getCoinCommunity(id: string): Promise<Community | null> {
  const res = await fetch(`${getApiUrl()}/api/coins/${id}/community`, { next: { revalidate: 30 } });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`API request failed: community (${res.status})`);
  return res.json();
}
