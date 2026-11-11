import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Plus Jakarta Sans"', "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono"', "monospace"],
      },
      fontSize: {
        "2xs": ["0.6875rem", { lineHeight: "1rem" }], // FIX: text-2xs is used in submit/contract/verify but was never defined
      },
      colors: {
        ink: "#0f172a",
        sea: {
          50: "#f0fdfa", 100: "#ccfbf1", 200: "#99f6e4", 300: "#5eead4", 400: "#2dd4bf",
          500: "#0d9488", 600: "#0f766e", 700: "#115e59", 800: "#134e4a", 900: "#0b3b38",
        },
        sand: { 50: "#fafaf9", 100: "#f5f5f4" },
        coral: { 100: "#ffe4e0", 500: "#f97360", 600: "#e5533d" },
      },
      borderRadius: { xl: "0.875rem", "2xl": "1.25rem", "3xl": "1.75rem" },
      boxShadow: {
        card: "0 1px 2px rgba(15,23,42,.04), 0 4px 12px -2px rgba(15,23,42,.05)",
        lift: "0 12px 32px -8px rgba(15,23,42,.14)",
        glow: "0 0 0 4px rgba(13,148,136,.15)",
      },
      keyframes: {
        "fade-up": { "0%": { opacity: "0", transform: "translateY(8px)" }, "100%": { opacity: "1", transform: "none" } },
        shimmer: { "100%": { transform: "translateX(100%)" } },
      },
      animation: { "fade-up": "fade-up .35s ease-out both" },
    },
  },
  plugins: [],
};
export default config;
