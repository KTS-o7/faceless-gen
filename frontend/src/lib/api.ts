import type { Job, ProjectSummary, ProjectDetail, AngleResponse, StoryBlockResponse, SceneResponse } from '../types'

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

// Projects
export async function createProject(name: string, source_doc: string, target_duration_minutes: number): Promise<ProjectDetail> {
  const res = await fetch('/api/projects', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name, source_doc, target_duration_minutes }) })
  return handleResponse(res)
}
export async function listProjects(): Promise<ProjectSummary[]> {
  return handleResponse(await fetch('/api/projects'))
}
export async function getProject(id: string): Promise<ProjectDetail> {
  return handleResponse(await fetch(`/api/projects/${id}`))
}
export async function deleteProject(id: string): Promise<void> {
  const res = await fetch(`/api/projects/${id}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`)
}
export async function updateProject(id: string, fields: Partial<ProjectSummary>): Promise<ProjectDetail> {
  const res = await fetch(`/api/projects/${id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(fields) })
  return handleResponse(res)
}

// Angles
export async function generateAngles(projectId: string): Promise<AngleResponse[]> {
  const res = await fetch(`/api/projects/${projectId}/angles/generate`, { method: 'POST' })
  return handleResponse(res)
}
export async function chooseAngle(projectId: string, angleId: string): Promise<AngleResponse> {
  const res = await fetch(`/api/projects/${projectId}/angles/${angleId}/choose`, { method: 'POST' })
  return handleResponse(res)
}

// Story
export async function generateStory(projectId: string): Promise<StoryBlockResponse[]> {
  const res = await fetch(`/api/projects/${projectId}/story/generate`, { method: 'POST' })
  return handleResponse(res)
}
export async function getStory(projectId: string): Promise<StoryBlockResponse[]> {
  return handleResponse(await fetch(`/api/projects/${projectId}/story`))
}
export async function reorderStory(projectId: string, orderedIds: string[]): Promise<StoryBlockResponse[]> {
  const res = await fetch(`/api/projects/${projectId}/story/reorder`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ordered_ids: orderedIds }) })
  return handleResponse(res)
}
export async function updateStoryBlock(projectId: string, blockId: string, content: string): Promise<StoryBlockResponse> {
  const res = await fetch(`/api/projects/${projectId}/story/${blockId}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ content }) })
  return handleResponse(res)
}
export async function deleteStoryBlock(projectId: string, blockId: string): Promise<void> {
  const res = await fetch(`/api/projects/${projectId}/story/${blockId}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`)
}
export async function confirmStory(projectId: string): Promise<ProjectSummary> {
  const res = await fetch(`/api/projects/${projectId}/story/confirm`, { method: 'POST' })
  return handleResponse(res)
}

// Scenes
export async function generateScenes(projectId: string): Promise<SceneResponse[]> {
  const res = await fetch(`/api/projects/${projectId}/scenes/generate`, { method: 'POST' })
  return handleResponse(res)
}
export async function getScenes(projectId: string): Promise<SceneResponse[]> {
  return handleResponse(await fetch(`/api/projects/${projectId}/scenes`))
}
export async function reorderScenes(projectId: string, orderedIds: string[]): Promise<SceneResponse[]> {
  const res = await fetch(`/api/projects/${projectId}/scenes/reorder`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ordered_ids: orderedIds }) })
  return handleResponse(res)
}
export async function updateScene(projectId: string, sceneId: string, fields: Partial<SceneResponse>): Promise<SceneResponse> {
  const res = await fetch(`/api/projects/${projectId}/scenes/${sceneId}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(fields) })
  return handleResponse(res)
}
export async function regenerateField(projectId: string, sceneId: string, fieldName: 'image_prompt' | 'video_prompt', storyContext: string, sourceDocExcerpt: string): Promise<SceneResponse> {
  const res = await fetch(`/api/projects/${projectId}/scenes/${sceneId}/regenerate`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ field_name: fieldName, story_context: storyContext, source_doc_excerpt: sourceDocExcerpt }) })
  return handleResponse(res)
}
export async function confirmScenes(projectId: string): Promise<ProjectSummary> {
  const res = await fetch(`/api/projects/${projectId}/scenes/confirm`, { method: 'POST' })
  return handleResponse(res)
}
