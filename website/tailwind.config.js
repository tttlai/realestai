/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      // Same palette and fonts as public/brokers/brokers.css.
      colors: {
        night: '#0a192f',
        'night-raised': '#14294a',
        'night-text': '#d5e0f5',
        mint: '#64ffda',
        'mint-soft': '#c9f5e8',
        day: '#eef4f1',
        'day-line': '#b9ccc5',
        ink: '#0b2033',
        'ink-soft': '#3c5263',
        teal: '#0b6656',
        snow: '#f4f8ff',
      },
      fontFamily: {
        display: ['"Anek Latin"', '"Trebuchet MS"', 'sans-serif'],
        sans: ['Mukta', '"Nirmala UI"', 'sans-serif'],
      },
    },
  },
  plugins: [],
};
