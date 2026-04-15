export type JobStatus = 'pending' | 'running' | 'done' | 'failed'

export interface Job {
  job_id: string
  status: JobStatus
  user_prompt: string
  progress_log: string[]
  final_output: string | null
  scene_thumbnails: string[]
  video_paths: string[]
  error: string | null
  created_at: string
}

export interface GenerateSettings {
  model: string
  voice_id: string
  clip_count: number
  video_backend: string
}
