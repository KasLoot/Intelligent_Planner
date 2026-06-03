/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        meituan: {
          DEFAULT: '#FFC300',
          light: '#FFF8E1',
          dark: '#E5AF00',
        },
      },
    },
  },
  plugins: [],
}