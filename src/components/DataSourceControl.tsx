'use client'

import { useState } from 'react'
import { Database } from 'lucide-react'

export type DataSource = 'yahoo' | 'futu'

interface DataSourceControlProps {
  dataSource: DataSource
  futuConnected: boolean
  onDataSourceChange: (source: DataSource) => void
}

export default function DataSourceControl({
  dataSource,
  futuConnected,
  onDataSourceChange,
}: DataSourceControlProps) {
  const [isAnimating, setIsAnimating] = useState(false)

  const handleToggle = (source: DataSource) => {
    if (source !== dataSource) {
      setIsAnimating(true)
      onDataSourceChange(source)
      setTimeout(() => setIsAnimating(false), 300)
    }
  }

  const isYahooConnected = true
  const isFutuConnected = futuConnected

  return (
    <div 
      className={`
        flex items-center h-9 rounded-lg overflow-hidden
        bg-secondary border border-border/50
        transition-all duration-200
        ${isAnimating ? 'scale-95 opacity-80' : 'scale-100 opacity-100'}
      `}
    >
      {/* Yahoo 按鈕連內置狀態燈 */}
      <button
        type="button"
        onClick={() => handleToggle('yahoo')}
        className={`
          h-full px-3 text-sm font-medium transition-all duration-200 cursor-pointer flex items-center gap-2
          ${dataSource === 'yahoo' 
            ? 'bg-primary text-primary-foreground' 
            : 'text-muted-foreground hover:text-foreground hover:bg-secondary/80'
          }
        `}
      >
        <span className={`w-2 h-2 rounded-full ${isYahooConnected ? 'bg-green-400' : 'bg-red-400'}`} />
        Yahoo
      </button>

      {/* 分隔線 */}
      <div className="w-px h-4 bg-border" />

      {/* 富途 按鈕連內置狀態燈 */}
      <button
        type="button"
        onClick={() => handleToggle('futu')}
        className={`
          h-full px-3 text-sm font-medium transition-all duration-200 cursor-pointer flex items-center gap-2
          ${dataSource === 'futu' 
            ? 'bg-primary text-primary-foreground' 
            : 'text-muted-foreground hover:text-foreground hover:bg-secondary/80'
          }
        `}
      >
        <span className={`w-2 h-2 rounded-full ${isFutuConnected ? 'bg-green-400' : 'bg-red-400'}`} />
        <Database className="w-3.5 h-3.5" />
        富途
      </button>
    </div>
  )
}
