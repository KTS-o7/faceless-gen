import { useEffect, useRef } from 'react'
import { AnimatePresence, motion } from 'framer-motion'

interface Props {
  logs: string[]
  isActive: boolean
}

export function ProgressLog({ logs, isActive }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs])

  if (logs.length === 0 && !isActive) return null

  return (
    <div className="mt-4 bg-zinc-900 border border-zinc-800 rounded-lg p-3 max-h-64 overflow-y-auto">
      <div className="flex items-center gap-2 mb-2">
        {isActive && (
          <span className="inline-flex items-center gap-1 text-xs bg-orange-500/20 text-orange-400 px-2 py-0.5 rounded-full">
            <span className="animate-pulse">●</span> Running
          </span>
        )}
      </div>
      <AnimatePresence initial={false}>
        {logs.map((log, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, x: -10 }}
            animate={{ opacity: 1, x: 0 }}
            className="font-mono text-xs text-zinc-300 py-0.5"
          >
            {log}
          </motion.div>
        ))}
      </AnimatePresence>
      <div ref={bottomRef} />
    </div>
  )
}
