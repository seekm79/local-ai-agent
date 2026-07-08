/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        panel: "#1e1e2e",
        panelalt: "#181825",
        edge: "#313244",
        accent: "#89b4fa",
      },
    },
  },
  plugins: [],
};
