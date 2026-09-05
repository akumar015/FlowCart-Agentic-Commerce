/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'flow-light': '#F9F7F7',
        'flow-muted': '#DBE2EF',
        'flow-accent': '#3F72AF',
        'flow-dark': '#112D4E',
      }
    },
  },
  plugins: [],
}
