/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#101b2d",
        shell: "#15233a",
        paper: "#f4f1e9",
        teal: "#3fd7c4",
        lime: "#c9ee72",
        coral: "#ff836f",
      },
      fontFamily: {
        sans: ["DM Sans", "ui-sans-serif", "sans-serif"],
        display: ["Space Grotesk", "DM Sans", "sans-serif"],
      },
      boxShadow: {
        soft: "0 18px 60px rgba(16, 27, 45, .12)",
      },
    },
  },
  plugins: [],
};
