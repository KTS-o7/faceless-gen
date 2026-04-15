import { useState, useRef } from 'react'
import { startGeneration, streamJobProgress } from '../lib/api'
import type { Job } from '../types'

export function useGenerate() {
  const [isGenerating, setIsGenerating] = useState(false)
  const [progressLog, setProgressLog] = useState<string[]>([])
  const [currentJob, setCurrentJob] = useState<Job | null>(null)
  const [error, setError] = useState<string | null>(null)
  const cleanupRef = useRef<(() => void) | null>(null)

  async function generate(prompt: string) {
    setIsGenerating(true)
    setProgressLog([])
    setCurrentJob(null)
    setError(null)
    try {
      const { job_id } = await startGeneration(prompt)
      cleanupRef.current = streamJobProgress(
        job_id,
        (msg) => setProgressLog((prev) => [...prev, msg]),
        (job) => { setCurrentJob(job); setIsGenerating(false) },
        (msg) => { setError(msg); setIsGenerating(false) }
      )
    } catch (e) {
      setError(String(e))
      setIsGenerating(false)
    }
  }

  function cancel() {
    cleanupRef.current?.()
    setIsGenerating(false)
  }

  return { isGenerating, progressLog, currentJob, error, generate, cancel }
}
