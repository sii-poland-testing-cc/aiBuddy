import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./lib/**/*.{js,ts,jsx,tsx,mdx}",
    "./node_modules/@llamaindex/chat-ui/dist/**/*.js",
  ],
  theme: {
    extend: {
      colors: {
        buddy: {
          base: "#141210",
          surface: "#1a1612",
          elevated: "#1e1a16",
          border: "#2a2520",
          "border-dark": "#3a3028",
          muted: "#4a3c2a",
          text: "#e8dcc8",
          "text-muted": "#8a7a68",
          "text-dim": "#6a5e52",
          "text-faint": "#5a4e42",
          "text-ghost": "#3a3028",
          gold: "#c8902a",
          "gold-light": "#f0c060",
          success: "#4a9e6b",
          error: "#c85a3a",
        },
      },
      fontFamily: {
        sans: ["var(--font-dm-sans)", "sans-serif"],
        mono: ["var(--font-dm-mono)", "monospace"],
      },
      keyframes: {
        "slide-in": {
          from: { transform: "translateX(-100%)" },
          to: { transform: "translateX(0)" },
        },
      },
      animation: {
        "slide-in": "slide-in 0.2s ease-out",
      },
    },
  },
  plugins: [],
};

export default config;
