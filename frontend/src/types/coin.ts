export interface Score {
  narrative_score: number | null;
  community_score: number | null;
  wallet_score: number | null;
  wallet_source: string | null;
  risk_score: number | null;
  liquidity_score: number | null;
  trend_score: number | null;
  overall_score: number | null;
  confidence: number | null;
  scoring_notes: string | null;
  updated_at: string;
}

export interface Coin {
  id: string;
  contract_address: string;
  pair_address: string | null;
  chain: string;
  source: string;
  symbol: string | null;
  name: string | null;
  launch_time: string | null;
  liquidity_usd: number | null;
  market_cap_usd: number | null;
  fdv_usd: number | null;
  volume_24h_usd: number | null;
  price_usd: number | null;
  price_change_1h: number | null;
  price_change_24h: number | null;
  is_active: boolean;
  first_seen_at: string;
  last_updated_at: string;
  score: Score | null;
}

export interface RiskFlag {
  flag_type: string;
  severity: "low" | "medium" | "high" | "critical";
  points: number;
  description: string;
  detected_at: string;
}

export interface Community {
  lookback_days: number;
  total_posts: number;
  unique_posters: number;
  engagement_total: number;
  avg_engagement_per_post: number | null;
  growth_rate_pct: number | null;
  organic_discussion_ratio: number | null;
  duplicate_content_ratio: number | null;
  reddit_subscribers: number | null;
  lunarcrush_galaxy_score: number | null;
  data_source: string;
  community_score: number | null;
  updated_at: string;
}

export interface Narrative {
  main_topic: string | null;
  meme_category: string | null;
  related_events: string | null;
  similar_historical_memes: string | null;
  emotion: string | null;
  is_funny: boolean | null;
  is_controversial: boolean | null;
  is_relatable: boolean | null;
  could_spread_beyond_crypto: boolean | null;
  narrative_summary: string | null;
  virality_score: number | null;
  narrative_score: number | null;
  post_count_analyzed: number;
  sources_used: string | null;
  updated_at: string;
}

export interface Wallet {
  id: string;
  chain: string;
  address: string;
  total_positions: number;
  positions_with_known_roi: number;
  wins: number;
  win_rate: number | null;
  avg_roi_pct: number | null;
  avg_hold_time_seconds: number | null;
  early_entry_count: number;
  early_entry_frequency: number | null;
  reputation_score: number | null;
  held_coins: HeldCoin[];
  first_seen_at: string;
  updated_at: string;
}

export interface HeldCoin {
  coin_id: string;
  symbol: string | null;
  still_holding: boolean;
}

export interface Alert {
  id: string;
  coin_id: string;
  coin_symbol: string | null;
  coin_chain: string | null;
  alert_type: string;
  severity: "info" | "warning" | "critical";
  message: string;
  trigger_value: number | null;
  previous_value: number | null;
  channels_delivered: string | null;
  delivered: boolean;
  created_at: string;
}

export interface HistoricalScorePoint {
  overall_score: number;
  liquidity_score: number | null;
  trend_score: number | null;
  recorded_at: string;
}

export interface PaperTrade {
  id: string;
  coin_id: string;
  symbol: string;
  chain: string;
  position_size_gbp: number;
  entry_price_usd: number;
  entry_overall_score: number;
  entry_risk_score: number | null;
  entry_at: string;
  exit_price_usd: number | null;
  exit_at: string | null;
  pnl_gbp: number | null;
  pnl_pct: number | null;
  status: "open" | "closed";
}

export interface PaperTradingSummary {
  total_trades: number;
  open_positions: number;
  closed_positions: number;
  win_count: number;
  win_rate_pct: number | null;
  closed_by_take_profit: number;
  closed_by_stop_loss: number;
  closed_by_timeout: number;
  total_realized_pnl_gbp: number;
  total_unrealized_pnl_gbp: number;
  total_pnl_gbp: number;
  entry_score_threshold: number;
  risk_gate_max: number;
  exit_gain_pct: number;
  stop_loss_pct: number;
  max_hold_hours: number;
}
