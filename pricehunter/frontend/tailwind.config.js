/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx,ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: '#0A0F1C',
        'ink-soft': '#11192B',
        mint: '#00FF88',
      },
      boxShadow: {
        soft: '0 24px 80px rgba(6, 12, 25, 0.45)',
      },
      fontFamily: {
        display: ['Satoshi', 'system-ui', 'sans-serif'],
        body: ['"DM Sans"', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
