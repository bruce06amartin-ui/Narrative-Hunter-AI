import { Narrative } from "@/types/coin";

export default function NarrativePanel({ narrative }: { narrative: Narrative | null }) {
  if (!narrative || !narrative.narrative_summary) {
    return (
      <div className="rounded-lg border border-dashed border-hairline bg-panel/50 px-4 py-8 text-center">
        <p className="font-mono text-xs text-ink-faint">
          No narrative analysis yet — needs at least one social source (Reddit/CryptoPanic/X)
          plus ANTHROPIC_API_KEY configured server-side.
        </p>
      </div>
    );
  }

  const tags = [
    narrative.meme_category,
    narrative.emotion,
    narrative.is_funny ? "funny" : null,
    narrative.is_controversial ? "controversial" : null,
    narrative.is_relatable ? "relatable" : null,
    narrative.could_spread_beyond_crypto ? "could spread beyond crypto" : null,
  ].filter(Boolean) as string[];

  return (
    <div className="space-y-3 rounded-lg border border-hairline bg-panel p-4">
      {narrative.main_topic && (
        <p className="font-display text-base font-semibold text-ink">{narrative.main_topic}</p>
      )}
      <p className="text-sm text-ink-muted">{narrative.narrative_summary}</p>

      {tags.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {tags.map((tag) => (
            <span
              key={tag}
              className="rounded-full border border-hairline px-2 py-0.5 font-mono text-[10px] uppercase tracking-wide text-ink-muted"
            >
              {tag}
            </span>
          ))}
        </div>
      )}

      {(narrative.related_events || narrative.similar_historical_memes) && (
        <div className="space-y-1 border-t border-hairline pt-3 text-xs text-ink-faint">
          {narrative.related_events && <p>Related events: {narrative.related_events}</p>}
          {narrative.similar_historical_memes && <p>Similar to: {narrative.similar_historical_memes}</p>}
        </div>
      )}

      <p className="font-mono text-[11px] text-ink-faint">
        Based on {narrative.post_count_analyzed} post(s) from {narrative.sources_used || "—"}.
      </p>
    </div>
  );
}
