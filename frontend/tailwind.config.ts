import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#1f2937",
        sea: { 50: "#ecfeff", 100: "#cffafe", 500: "#0891b2", 600: "#0e7490", 700: "#155e75" },
      },
    },
  },
  plugins: [],
};

export default config;
