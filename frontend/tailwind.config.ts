import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        void: "#0A0D12",
        panel: "#12161D",
        "panel-raised": "#1A2029",
        hairline: "#232A35",
        amber: {
          DEFAULT: "#FFB020",
          dim: "#8A6420",
        },
        mint: "#3ECF8E",
        alert: "#FF5A5F",
        ink: {
          DEFAULT: "#E8EAED",
          muted: "#6B7684",
          faint: "#3E4653",
        },
      },
      fontFamily: {
        display: ["var(--font-display)", "sans-serif"],
        body: ["var(--font-body)", "sans-serif"],
        mono: ["var(--font-mono)", "monospace"],
      },
      animation: {
        ticker: "ticker 40s linear infinite",
      },
      keyframes: {
        ticker: {
          "0%": { transform: "translateX(0)" },
          "100%": { transform: "translateX(-50%)" },
        },
      },
    },
  },
  plugins: [],
};

export default config;
