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

export interface ProjectSummary {
  id: string
  name: string
  stage: string
  target_duration_minutes: number
  aspect_ratio: string | null
  music_track: string | null
  active_job_id: string | null
  created_at: string
  updated_at: string
}

export interface AngleResponse {
  id: string
  order: number
  title: string
  pitch: string
  chosen: boolean
}

export interface StoryBlockResponse {
  id: string
  order: number
  content: string
}

export interface SceneResponse {
  id: string
  order: number
  title: string
  dialog: string
  image_prompt: string
  video_prompt: string
  audio_path: string | null
  video_clip_path: string | null
  thumbnail_path: string | null
  image_path: string | null
  audio_duration_seconds: number | null
}

export interface ProjectDetail extends ProjectSummary {
  source_doc: string
  final_output_path: string | null
  error: string | null
  angles: AngleResponse[]
  story_blocks: StoryBlockResponse[]
  scenes: SceneResponse[]
}
