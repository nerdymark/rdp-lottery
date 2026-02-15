import { useEffect, useRef, useState } from 'react'

export default function SlotMachineLog() {
  const [lines, setLines] = useState<string[]>([])
  const [spinning, setSpinning] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  // Load initial logs then connect SSE
  useEffect(() => {
    fetch('/api/logs')
      .then((r) => r.json())
      .then((data) => setLines(data.logs ?? []))
      .catch(() => {})

    const es = new EventSource('/api/logs/stream')
    es.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data)
        if (msg.type === 'log' && msg.line) {
          setSpinning(true)
          setLines((prev) => [...prev.slice(-200), msg.line])
          setTimeout(() => setSpinning(false), 600)
        }
      } catch {
        // ignore parse errors
      }
    }
    return () => es.close()
  }, [])

  // Auto-scroll to bottom
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [lines])

  return (
    <div className="casino-card overflow-hidden">
      {/* Slot machine header */}
      <div className="bg-gradient-to-r from-casino-red via-casino-red-bright to-casino-red px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className={`text-2xl ${spinning ? 'animate-spin' : ''}`}>🎰</div>
          <h3 className="font-display text-lg font-black text-white tracking-wide">
            LIVE FEED
          </h3>
        </div>
        <div className="flex gap-1.5">
          {/* Decorative slot machine lights */}
          <Light color="yellow" blink={spinning} />
          <Light color="green" blink={spinning} delay={100} />
          <Light color="yellow" blink={spinning} delay={200} />
          <Light color="green" blink={spinning} delay={300} />
          <Light color="yellow" blink={spinning} delay={400} />
        </div>
      </div>

      {/* Reel display area */}
      <div className="relative">
        {/* Top shadow for reel effect */}
        <div className="absolute top-0 left-0 right-0 h-8 bg-gradient-to-b from-black/80 to-transparent z-10 pointer-events-none" />
        {/* Bottom shadow */}
        <div className="absolute bottom-0 left-0 right-0 h-8 bg-gradient-to-t from-black/80 to-transparent z-10 pointer-events-none" />

        {/* Log lines - the "reels" */}
        <div
          ref={containerRef}
          className="h-64 overflow-y-auto bg-black/70 px-4 py-4 font-mono text-xs leading-relaxed scrollbar-thin"
          style={{
            backgroundImage:
              'repeating-linear-gradient(0deg, transparent, transparent 23px, rgba(212, 168, 67, 0.05) 23px, rgba(212, 168, 67, 0.05) 24px)',
          }}
        >
          {lines.length === 0 ? (
            <div className="flex items-center justify-center h-full text-gray-600 italic">
              Insert coin to begin...
            </div>
          ) : (
            lines.map((line, i) => <LogLine key={i} line={line} isNew={i === lines.length - 1 && spinning} />)
          )}
          <div ref={bottomRef} />
        </div>
      </div>

      {/* Bottom bar with line count */}
      <div className="bg-black/50 px-4 py-2 flex items-center justify-between border-t border-casino-gold/10">
        <span className="text-gray-600 text-xs font-mono">
          {lines.length} lines
        </span>
        <div className="flex items-center gap-2">
          <span className={`w-2 h-2 rounded-full ${spinning ? 'bg-casino-neon animate-pulse' : 'bg-gray-600'}`} />
          <span className="text-gray-500 text-xs">
            {spinning ? 'ROLLING...' : 'WAITING'}
          </span>
        </div>
      </div>
    </div>
  )
}

function LogLine({ line, isNew }: { line: string; isNew: boolean }) {
  // Color-code by log level
  let color = 'text-gray-400'
  if (line.includes('[ERROR]')) color = 'text-casino-red-bright'
  else if (line.includes('[WARNING]')) color = 'text-yellow-400'
  else if (line.includes('[INFO]') && (line.includes('RDP') || line.includes('rdp_open')))
    color = 'text-casino-neon'
  else if (line.includes('Discovery complete') || line.includes('completed'))
    color = 'text-casino-gold'

  return (
    <div
      className={`${color} ${isNew ? 'slot-line-enter' : ''} whitespace-pre-wrap break-all py-0.5`}
    >
      {line}
    </div>
  )
}

function Light({ color, blink, delay = 0 }: { color: string; blink: boolean; delay?: number }) {
  const bg = color === 'yellow' ? 'bg-yellow-400' : 'bg-green-400'
  const shadow = color === 'yellow' ? 'shadow-yellow-400/50' : 'shadow-green-400/50'
  return (
    <span
      className={`w-3 h-3 rounded-full inline-block ${bg} ${blink ? `shadow-lg ${shadow}` : 'opacity-30'}`}
      style={{
        animation: blink ? `blink-light 0.4s ease-in-out ${delay}ms infinite alternate` : 'none',
      }}
    />
  )
}
