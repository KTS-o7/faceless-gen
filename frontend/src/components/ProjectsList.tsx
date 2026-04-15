import { useState, useEffect, useCallback } from 'react'
import { listProjects, createProject, deleteProject, getProject } from '../lib/api'
import type { ProjectSummary, ProjectDetail } from '../types'

const STAGE_COLORS: Record<string, string> = {
  angle_selection: 'text-yellow-400 bg-yellow-500/10',
  story_editing: 'text-blue-400 bg-blue-500/10',
  scene_editing: 'text-purple-400 bg-purple-500/10',
  music_selection: 'text-pink-400 bg-pink-500/10',
  generating: 'text-orange-400 bg-orange-500/10',
  done: 'text-green-400 bg-green-500/10',
  failed: 'text-red-400 bg-red-500/10',
}

interface Props {
  onOpenProject: (project: ProjectDetail) => void
}

export function ProjectsList({ onOpenProject }: Props) {
  const [projects, setProjects] = useState<ProjectSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [name, setName] = useState('')
  const [doc, setDoc] = useState('')
  const [duration, setDuration] = useState(5)
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try { setProjects(await listProjects()) }
    finally { setLoading(false) }
  }, [])

  useEffect(() => {
    load()
    const id = setInterval(load, 5000)
    return () => clearInterval(id)
  }, [load])

  async function handleCreate() {
    if (!name.trim() || !doc.trim()) return
    setCreating(true)
    setError(null)
    try {
      const project = await createProject(name.trim(), doc.trim(), duration)
      setShowCreate(false)
      setName(''); setDoc(''); setDuration(5)
      onOpenProject(project)
    } catch (e) {
      setError(String(e))
    } finally {
      setCreating(false)
    }
  }

  async function handleDelete(id: string) {
    if (!confirm('Delete this project? This cannot be undone.')) return
    await deleteProject(id)
    load()
  }

  function timeAgo(iso: string) {
    const diff = Date.now() - new Date(iso).getTime()
    const h = Math.floor(diff / 3600000)
    if (h < 1) return `${Math.floor(diff / 60000)}m ago`
    if (h < 24) return `${h}h ago`
    return `${Math.floor(h / 24)}d ago`
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-semibold">Projects</h2>
        <button onClick={() => setShowCreate(true)}
          className="bg-orange-500 hover:bg-orange-600 px-4 py-1.5 rounded text-sm font-medium transition-colors">
          + New Project
        </button>
      </div>

      {showCreate && (
        <div className="bg-zinc-900 border border-zinc-700 rounded-lg p-5 mb-6 space-y-4">
          <h3 className="font-medium">New Project</h3>
          <div>
            <label className="text-xs text-zinc-400 block mb-1">Project name</label>
            <input value={name} onChange={e => setName(e.target.value)}
              className="w-full bg-zinc-800 border border-zinc-700 rounded px-3 py-2 text-sm focus:outline-none focus:border-orange-500" />
          </div>
          <div>
            <label className="text-xs text-zinc-400 block mb-1">Target duration: {duration} min</label>
            <input type="range" min={1} max={15} value={duration} onChange={e => setDuration(+e.target.value)}
              className="w-full accent-orange-500" />
          </div>
          <div>
            <label className="text-xs text-zinc-400 block mb-1">Paste research doc (Markdown)</label>
            <textarea value={doc} onChange={e => setDoc(e.target.value)} rows={6}
              placeholder="Paste your research document here..."
              className="w-full bg-zinc-800 border border-zinc-700 rounded px-3 py-2 text-sm resize-y focus:outline-none focus:border-orange-500" />
          </div>
          {error && <p className="text-xs text-red-400">{error}</p>}
          <div className="flex gap-2">
            <button onClick={handleCreate} disabled={!name.trim() || !doc.trim() || creating}
              className="bg-orange-500 hover:bg-orange-600 disabled:opacity-50 px-4 py-1.5 rounded text-sm font-medium">
              {creating ? 'Creating...' : 'Create Project'}
            </button>
            <button onClick={() => setShowCreate(false)} className="text-zinc-400 hover:text-white px-4 py-1.5 rounded text-sm">
              Cancel
            </button>
          </div>
        </div>
      )}

      {loading ? (
        <p className="text-zinc-500 text-sm">Loading...</p>
      ) : projects.length === 0 ? (
        <div className="text-center py-20 text-zinc-600">
          <p className="text-4xl mb-2">🎬</p>
          <p>No projects yet. Create one to get started.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {projects.map(p => (
            <div key={p.id} className="bg-zinc-900 border border-zinc-800 rounded-lg p-4 flex items-center justify-between">
              <div>
                <p className="font-medium text-sm">{p.name}</p>
                <div className="flex items-center gap-2 mt-1">
                  <span className={`text-xs px-2 py-0.5 rounded-full ${STAGE_COLORS[p.stage] ?? 'text-zinc-400 bg-zinc-800'}`}>
                    {p.stage.replace('_', ' ')}
                  </span>
                  <span className="text-xs text-zinc-500">{timeAgo(p.created_at)}</span>
                </div>
              </div>
              <div className="flex gap-2">
                <button onClick={async () => { const full = await getProject(p.id); onOpenProject(full) }}
                  className="text-xs bg-zinc-800 hover:bg-zinc-700 px-3 py-1.5 rounded">
                  Open
                </button>
                <button onClick={() => handleDelete(p.id)}
                  className="text-xs text-red-400 hover:text-red-300 px-3 py-1.5 rounded">
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
