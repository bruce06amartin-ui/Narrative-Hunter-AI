"use client";

import {
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  CartesianGrid,
} from "recharts";
import { HistoricalScorePoint } from "@/types/coin";

export default function ScoreHistoryChart({ points }: { points: HistoricalScorePoint[] }) {
  if (points.length < 2) {
    return (
      <div className="flex h-56 items-center justify-center rounded-lg border border-dashed border-hairline bg-panel/50">
        <p className="font-mono text-xs text-ink-faint">
          Not enough score history yet — check back after a few scoring cycles.
        </p>
      </div>
    );
  }

  const data = points.map((p) => ({
    time: new Date(p.recorded_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    overall: Math.round(p.overall_score),
  }));

  return (
    <div className="h-56 rounded-lg border border-hairline bg-panel p-2">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 10, right: 12, left: -12, bottom: 0 }}>
          <CartesianGrid stroke="#232A35" strokeDasharray="3 3" vertical={false} />
          <XAxis
            dataKey="time"
            stroke="#6B7684"
            fontSize={10}
            tickLine={false}
            axisLine={{ stroke: "#232A35" }}
          />
          <YAxis
            domain={[0, 100]}
            stroke="#6B7684"
            fontSize={10}
            tickLine={false}
            axisLine={{ stroke: "#232A35" }}
          />
          <Tooltip
            contentStyle={{
              background: "#12161D",
              border: "1px solid #232A35",
              borderRadius: 6,
              fontSize: 12,
              fontFamily: "var(--font-mono)",
            }}
            labelStyle={{ color: "#6B7684" }}
            itemStyle={{ color: "#FFB020" }}
          />
          <Line
            type="monotone"
            dataKey="overall"
            stroke="#FFB020"
            strokeWidth={2}
            dot={false}
            name="Overall Score"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
