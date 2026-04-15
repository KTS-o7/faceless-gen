import { useState, useEffect, useCallback } from 'react'
import { getHistory } from '../lib/api'
import type { Job } from '../types'

export function useHistory() {
  const [jobs, setJobs] = useState<Job[]>([])
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const data = await getHistory()
      setJobs(data)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
    const id = setInterval(refresh, 4000)
    return () => clearInterval(id)
  }, [refresh])

  return { jobs, loading, refresh }
}
