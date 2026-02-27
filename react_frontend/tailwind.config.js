/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./src/**/*.{js,jsx,ts,tsx}', './public/index.html'],
  theme: {
    extend: {
      colors: {
        'cyber-blue': '#19d3ff',
        'neon-red': '#ff2056',
        'alert-yellow': '#ffd84d',
      },
      backdropBlur: {
        xs: '2px',
        cyber: '18px',
      },
      boxShadow: {
        neon: '0 0 18px rgba(25, 211, 255, 0.35), 0 0 34px rgba(25, 211, 255, 0.2)',
        sos: '0 0 20px rgba(255, 32, 86, 0.55), 0 0 36px rgba(255, 32, 86, 0.3)',
      },
    },
  },
  plugins: [],
};
