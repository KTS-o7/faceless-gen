import type { Job } from '../types'

const BASE = '/api'

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`)
  return res.json()
}

export async function startGeneration(prompt: string): Promise<{ job_id: string; status: string }> {
  const res = await fetch(`${BASE}/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_prompt: prompt }),
  })
  return handleResponse(res)
}

export async function getHistory(): Promise<Job[]> {
  const res = await fetch(`${BASE}/history`)
  return handleResponse(res)
}

export async function getJob(jobId: string): Promise<Job> {
  const res = await fetch(`${BASE}/history/${jobId}`)
  return handleResponse(res)
}

export function streamJobProgress(
  jobId: string,
  onProgress: (msg: string) => void,
  onDone: (job: Job) => void,
  onError: (msg: string) => void
): () => void {
  const es = new EventSource(`${BASE}/generate/${jobId}/stream`)
  es.addEventListener('progress', (e) => onProgress(e.data))
  es.addEventListener('done', (e) => { onDone(JSON.parse(e.data)); es.close() })
  es.addEventListener('error', (e) => { onError((e as MessageEvent).data ?? 'Stream error'); es.close() })
  return () => es.close()
}
