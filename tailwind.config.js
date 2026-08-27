/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        studio: {
          bg: "#0A0D14",
          card: "#121622",
          cardHover: "#182030",
          border: "#1E2638",
          cyan: "#00E5FF",
          green: "#00E676",
          purple: "#AB47BC",
          blue: "#0288D1",
        },
      },
    },
  },
  plugins: [],
};
