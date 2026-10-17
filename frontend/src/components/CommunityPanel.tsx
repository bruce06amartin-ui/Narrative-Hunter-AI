import { Community } from "@/types/coin";
import { formatPercent } from "@/lib/format";

export default function CommunityPanel({ community }: { community: Community | null }) {
  if (!community || community.total_posts === 0) {
    return (
      <div className="rounded-lg border border-dashed border-hairline bg-panel/50 px-4 py-8 text-center">
        <p className="font-mono text-xs text-ink-faint">
          No community data yet — needs posts collected by the Narrative Scanner
          (Reddit/CryptoPanic/X) within the lookback window.
        </p>
      </div>
    );
  }

  const growth = community.growth_rate_pct;
  const organicPct = community.organic_discussion_ratio !== null ? community.organic_discussion_ratio * 100 : null;
  const dupPct = community.duplicate_content_ratio !== null ? community.duplicate_content_ratio * 100 : null;

  return (
    <div className="rounded-lg border border-hairline bg-panel p-4">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Metric label="Posts" value={String(community.total_posts)} sub={`${community.lookback_days}d window`} />
        <Metric label="Unique Posters" value={String(community.unique_posters)} />
        <Metric
          label="Growth"
          value={growth === null ? "—" : formatPercent(growth)}
          tone={growth !== null && growth < 0 ? "alert" : growth !== null && growth > 0 ? "mint" : "default"}
          sub="vs prior window"
        />
        <Metric
          label="Organic"
          value={organicPct === null ? "—" : `${organicPct.toFixed(0)}%`}
          sub="unique posters / posts"
        />
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-4 border-t border-hairline pt-3 font-mono text-[11px] text-ink-faint">
        <span>
          Avg engagement:{" "}
          <span className="text-ink-muted">
            {community.avg_engagement_per_post?.toFixed(1) ?? "—"}
          </span>
        </span>
        <span>
          Duplicate content:{" "}
          <span className={dupPct !== null && dupPct > 30 ? "text-alert" : "text-ink-muted"}>
            {dupPct === null ? "—" : `${dupPct.toFixed(0)}%`}
          </span>
        </span>
        {community.reddit_subscribers !== null && (
          <span>
            Subreddit subscribers: <span className="text-ink-muted">{community.reddit_subscribers.toLocaleString()}</span>
          </span>
        )}
        {community.lunarcrush_galaxy_score !== null && (
          <span>
            LunarCrush Galaxy Score: <span className="text-amber">{community.lunarcrush_galaxy_score.toFixed(0)}</span>
          </span>
        )}
      </div>
      {community.data_source === "lunarcrush" && (
        <p className="mt-2 font-mono text-[11px] text-ink-faint border-t border-hairline pt-2">
          No posts collected yet for this coin — score is based entirely on LunarCrush's external tracking.
        </p>
      )}
    </div>
  );
}

function Metric({
  label,
  value,
  sub,
  tone = "default",
}: {
  label: string;
  value: string;
  sub?: string;
  tone?: "default" | "mint" | "alert";
}) {
  const color = { default: "text-ink", mint: "text-mint", alert: "text-alert" }[tone];
  return (
    <div>
      <p className="font-mono text-[10px] uppercase tracking-wider text-ink-muted">{label}</p>
      <p className={`mt-0.5 font-mono text-lg font-semibold ${color}`}>{value}</p>
      {sub && <p className="text-[10px] text-ink-faint">{sub}</p>}
    </div>
  );
}
