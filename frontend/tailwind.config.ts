import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#0f172a",
        lens: { 50: "#eef6ff", 100: "#d9eaff", 500: "#3b82f6", 600: "#2563eb", 700: "#1d4ed8" },
      },
    },
  },
  plugins: [],
};

export default config;
