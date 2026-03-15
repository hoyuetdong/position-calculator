import type { Config } from 'tailwindcss'

const config: Config = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        background: '#141414',
        foreground: '#e5e5e5',
        card: { DEFAULT: '#1c1c1c', foreground: '#e5e5e5' },
        primary: { DEFAULT: '#00ff88', foreground: '#141414' },
        secondary: { DEFAULT: '#262626', foreground: '#e5e5e5' },
        muted: { DEFAULT: '#2d2d2d', foreground: '#999999' },
        accent: { DEFAULT: '#383838', foreground: '#e5e5e5' },
        destructive: { DEFAULT: '#ff4d4d', foreground: '#e5e5e5' },
        border: '#383838',
        ring: '#00ff88',
        profit: '#00ff88',
        loss: '#ff4d4d',
        warning: '#ffaa00',
      },
    },
  },
  plugins: [],
}
export default config
