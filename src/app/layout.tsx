import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'

const inter = Inter({ subsets: ['latin'] })

export const metadata: Metadata = {
  title: 'Position Calculator',
  description: '專業交易倉位計算器 - VCP/CANSLIM 風格 (Yahoo Finance API)',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="zh-HK" className="dark" suppressHydrationWarning>
      <head>
        <style dangerouslySetInnerHTML={{__html: `
          html { background: #141414 !important; }
          html.dark { color-scheme: dark; }
          body { background: #141414 !important; color: #e5e5e5 !important; }
        `}} />
      </head>
      <body className={inter.className} style={{backgroundColor: '#141414', color: '#e5e5e5'}} suppressHydrationWarning>
        {children}
      </body>
    </html>
  )
}
