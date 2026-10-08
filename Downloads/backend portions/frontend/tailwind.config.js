/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        // TruthGuard AI design system (see README -> Design Tokens)
        navy: {
          DEFAULT: '#0A192F', // app background
          card: '#112240', // card / panel background
          border: '#233554', // subtle borders
        },
        teal: {
          DEFAULT: '#64FFDA', // accent / primary
          dim: 'rgba(100, 255, 218, 0.1)',
        },
        ink: {
          DEFAULT: '#E6F1FF', // primary text
          muted: '#8892B0', // secondary text
        },
        danger: '#FF4D4D',
        warn: '#FFD166',
        safe: '#4ADE80',
      },
      fontFamily: {
        sans: ['Inter', 'Poppins', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        display: ['Poppins', 'Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      },
      borderRadius: {
        card: '10px',
        DEFAULT: '8px',
      },
      boxShadow: {
        card: '0 10px 30px -10px rgba(2, 12, 27, 0.7)',
        glow: '0 0 0 1px rgba(100,255,218,0.25), 0 8px 30px -12px rgba(100,255,218,0.35)',
      },
      keyframes: {
        'fade-up': {
          '0%': { opacity: '0', transform: 'translateY(8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        blink: {
          '0%, 80%, 100%': { opacity: '0.2' },
          '40%': { opacity: '1' },
        },
        'spin-slow': {
          to: { transform: 'rotate(360deg)' },
        },
      },
      animation: {
        'fade-up': 'fade-up 260ms ease-out both',
        blink: 'blink 1.4s infinite both',
        'spin-slow': 'spin-slow 1.1s linear infinite',
      },
    },
  },
  plugins: [],
}
