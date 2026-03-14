import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'

const inter = Inter({ subsets: ['latin'] })

export const metadata: Metadata = {
  title: 'VCP Position Calculator - Yahoo Finance 版',
  description: '專業交易倉位計算器 - VCP/CANSLIM 風格 (Yahoo Finance API)',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="zh-HK" className="dark">
      <body className={inter.className}>{children}</body>
    </html>
  )
}
