/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // Surface
        bg: { DEFAULT: "#0B0D10", subtle: "#13161B", elevated: "#1A1E25" },
        border: { DEFAULT: "#272B33", strong: "#3A3F49" },
        // Text
        fg: { DEFAULT: "#E6E8EB", muted: "#9BA1A8", subtle: "#6B7177" },
        // Accent
        accent: { DEFAULT: "#7C5CFF", hover: "#6B4DEB" },
        // Semantic
        success: "#3DD68C",
        warning: "#F0A04B",
        danger: "#FF5C5C",
      },
      fontFamily: {
        sans: ["Inter Variable", "Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono Variable", "JetBrains Mono", "monospace"],
      },
      fontFeatureSettings: {
        nums: '"tnum", "cv11"',
      },
    },
  },
  plugins: [],
};
