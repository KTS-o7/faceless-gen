import { useState, useEffect } from 'react'
import { ProgressLog } from '../ProgressLog'
import { streamJobProgress } from '../../lib/api'
import type { ProjectDetail, Job } from '../../types'

interface Props {
  project: ProjectDetail
  onProjectUpdate: (p: ProjectDetail) => void
  onNewProject: () => void
}

export function GenerateStep({ project, onProjectUpdate, onNewProject }: Props) {
  const [generating, setGenerating] = useState(false)
  const [progressLog, setProgressLog] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)

  // On mount: if already generating, reconnect SSE
  useEffect(() => {
    if (project.stage === 'generating' && project.active_job_id) {
      reconnectSSE(project.active_job_id)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function reconnectSSE(jobId: string) {
    setGenerating(true)
    streamJobProgress(
      jobId,
      msg => setProgressLog(prev => [...prev, msg]),
      (_job: Job) => {
        setGenerating(false)
        // Refresh project to get updated stage/final_output_path
        fetch(`/api/projects/${project.id}`)
          .then(r => r.json())
          .then(onProjectUpdate)
          .catch(() => {})
      },
      msg => {
        setGenerating(false)
        setError(msg)
      },
    )
  }

  async function handleGenerate() {
    setGenerating(true)
    setProgressLog([])
    setError(null)
    try {
      const res = await fetch(`/api/projects/${project.id}/generate`, { method: 'POST' })
      if (!res.ok) {
        const data = await res.json().catch(() => ({ detail: res.statusText }))
        throw new Error(data.detail ?? res.statusText)
      }
      const { job_id } = await res.json()
      reconnectSSE(job_id)
    } catch (e) {
      setGenerating(false)
      setError(String(e))
    }
  }

  // Done state
  if (project.stage === 'done' && project.final_output_path) {
    const outputUrl = `/outputs/${project.id}/final.mp4`
    const thumbs = project.scenes.filter(s => s.thumbnail_path)
    return (
      <div className="space-y-4">
        <h2 className="text-lg font-semibold text-green-400">Generation Complete</h2>
        <video controls src={outputUrl} className="w-full rounded-lg border border-zinc-800" />
        {thumbs.length > 0 && (
          <div className="flex gap-2 overflow-x-auto pb-1">
            {thumbs.map((scene, i) => (
              <img
                key={scene.id}
                src={`/outputs/${project.id}/${scene.thumbnail_path}`}
                alt={`Scene ${i + 1}`}
                className="h-16 w-28 object-cover rounded flex-shrink-0"
                onError={e => {
                  ;(e.target as HTMLImageElement).style.display = 'none'
                }}
              />
            ))}
          </div>
        )}
        <div className="flex gap-3">
          <a
            href={outputUrl}
            download={`${project.name}.mp4`}
            className="bg-zinc-800 hover:bg-zinc-700 px-4 py-2 rounded text-sm font-medium"
          >
            Download MP4
          </a>
          <button
            onClick={onNewProject}
            className="text-zinc-400 hover:text-white px-4 py-2 rounded text-sm"
          >
            Start New Project
          </button>
        </div>
      </div>
    )
  }

  // Failed state
  if (project.stage === 'failed' && !generating) {
    return (
      <div className="space-y-4">
        <h2 className="text-lg font-semibold text-red-400">Generation Failed</h2>
        {project.error && (
          <pre className="text-xs text-red-400 bg-red-950/30 border border-red-900 rounded p-3 overflow-auto">
            {project.error}
          </pre>
        )}
        <button
          onClick={handleGenerate}
          className="bg-orange-500 hover:bg-orange-600 px-5 py-2 rounded font-medium text-sm"
        >
          Retry Generation
        </button>
      </div>
    )
  }

  // Pre-generation / generating state
  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">Generate Video</h2>

      {!generating && (
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4 space-y-2 text-sm">
          <div className="flex justify-between">
            <span className="text-zinc-400">Scenes</span>
            <span>{project.scenes.length}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-zinc-400">Aspect ratio</span>
            <span>{project.aspect_ratio ?? '—'}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-zinc-400">Music</span>
            <span>{project.music_track ?? 'No music'}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-zinc-400">Est. duration</span>
            <span>~{project.target_duration_minutes} min</span>
          </div>
        </div>
      )}

      {error && (
        <div className="text-sm text-red-400 bg-red-950/30 border border-red-900 rounded p-3">
          {error}
        </div>
      )}

      <ProgressLog logs={progressLog} isActive={generating} />

      {!generating && (
        <button
          onClick={handleGenerate}
          className="bg-orange-500 hover:bg-orange-600 px-5 py-2 rounded font-medium text-sm"
        >
          Generate Video
        </button>
      )}

      {generating && (
        <p className="text-sm text-zinc-400 animate-pulse">
          Generating — this may take a while...
        </p>
      )}
    </div>
  )
}
