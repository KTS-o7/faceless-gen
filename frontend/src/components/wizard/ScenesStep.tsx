import { useState, useEffect } from 'react'
import { DndContext, closestCenter } from '@dnd-kit/core'
import { SortableContext, verticalListSortingStrategy, useSortable, arrayMove } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { generateScenes, reorderScenes, updateScene, regenerateField, confirmScenes, updateProject } from '../../lib/api'
import { WizardSkeleton } from './WizardSkeleton'
import type { ProjectDetail, SceneResponse } from '../../types'
import type { DragEndEvent } from '@dnd-kit/core'

type EditableField = 'title' | 'dialog' | 'image_prompt' | 'video_prompt'

function SortableScene({
  scene,
  projectId,
  storyContext,
  sourceDocExcerpt,
  onUpdate,
}: {
  scene: SceneResponse
  projectId: string
  storyContext: string
  sourceDocExcerpt: string
  onUpdate: (updated: SceneResponse) => void
}) {
  const { attributes, listeners, setNodeRef, transform, transition } = useSortable({ id: scene.id })
  const [expanded, setExpanded] = useState(false)
  const [regen, setRegen] = useState<'image_prompt' | 'video_prompt' | null>(null)
  const [fields, setFields] = useState<Record<EditableField, string>>({
    title: scene.title,
    dialog: scene.dialog,
    image_prompt: scene.image_prompt,
    video_prompt: scene.video_prompt,
  })

  async function handleBlur(field: EditableField) {
    const original = scene[field as keyof SceneResponse] as string
    if (fields[field] !== original) {
      const updated = await updateScene(projectId, scene.id, { [field]: fields[field] })
      onUpdate(updated)
    }
  }

  async function handleRegen(field: 'image_prompt' | 'video_prompt') {
    setRegen(field)
    try {
      const updated = await regenerateField(projectId, scene.id, field, storyContext, sourceDocExcerpt)
      setFields(prev => ({ ...prev, [field]: updated[field] }))
      onUpdate(updated)
    } finally {
      setRegen(null)
    }
  }

  return (
    <div
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className="bg-zinc-900 border border-zinc-800 rounded-lg overflow-hidden"
    >
      <div
        className="flex items-center gap-3 p-3 cursor-pointer"
        onClick={() => setExpanded(e => !e)}
      >
        <button
          {...attributes}
          {...listeners}
          className="text-zinc-600 hover:text-zinc-400 cursor-grab text-lg leading-none"
          onClick={e => e.stopPropagation()}
        >
          ⠿
        </button>
        <span className="text-xs text-zinc-500 w-6">{scene.order + 1}</span>
        <p className="flex-1 text-sm font-medium truncate">{fields.title}</p>
        <span className="text-zinc-500 text-xs">{expanded ? '▲' : '▼'}</span>
      </div>

      {expanded && (
        <div className="border-t border-zinc-800 p-4 space-y-4">
          {(['title', 'dialog', 'image_prompt', 'video_prompt'] as const).map(field => (
            <div key={field}>
              <div className="flex items-center justify-between mb-1">
                <label className="text-xs text-zinc-400 capitalize">
                  {field.replace('_', ' ')}
                </label>
                {(field === 'image_prompt' || field === 'video_prompt') && (
                  <button
                    onClick={() => handleRegen(field)}
                    disabled={regen !== null}
                    className="text-xs text-zinc-500 hover:text-orange-400 disabled:opacity-50"
                  >
                    {regen === field ? '⟳ ...' : '↺ Regen'}
                  </button>
                )}
              </div>
              <textarea
                value={fields[field]}
                onChange={e => setFields(prev => ({ ...prev, [field]: e.target.value }))}
                onBlur={() => handleBlur(field)}
                rows={field === 'title' ? 1 : 3}
                className="w-full bg-zinc-800 border border-zinc-700 rounded px-3 py-2 text-sm resize-y focus:outline-none focus:border-orange-500"
              />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

interface Props {
  project: ProjectDetail
  onContinue: () => void
  onProjectUpdate: (p: ProjectDetail) => void
}

export function ScenesStep({ project, onContinue, onProjectUpdate: _onProjectUpdate }: Props) {
  const [scenes, setScenes] = useState<SceneResponse[]>(project.scenes)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [confirming, setConfirming] = useState(false)
  const [aspectRatio, setAspectRatio] = useState<string>(project.aspect_ratio ?? '')

  useEffect(() => {
    if (scenes.length === 0) loadScenes()
  }, [])

  async function loadScenes() {
    setLoading(true)
    setError(null)
    try {
      setScenes(await generateScenes(project.id))
    } catch (e) {
      setError(
        e instanceof Error && e.message.includes('422')
          ? 'The AI returned an unexpected response. Try regenerating.'
          : String(e)
      )
    } finally {
      setLoading(false)
    }
  }

  async function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event
    if (!over || active.id === over.id) return
    const oldIdx = scenes.findIndex(s => s.id === active.id)
    const newIdx = scenes.findIndex(s => s.id === over.id)
    const reordered = arrayMove(scenes, oldIdx, newIdx)
    setScenes(reordered)
    await reorderScenes(project.id, reordered.map(s => s.id))
  }

  async function handleAspectRatio(ar: string) {
    setAspectRatio(ar)
    await updateProject(project.id, { aspect_ratio: ar })
  }

  async function handleConfirm() {
    setConfirming(true)
    try {
      await confirmScenes(project.id)
      onContinue()
    } finally {
      setConfirming(false)
    }
  }

  const storyContext = project.story_blocks.map(b => b.content).join(' ').slice(0, 500)
  const sourceDocExcerpt = project.source_doc.slice(0, 1000)

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Edit Scenes</h2>
        <button
          onClick={() => { if (confirm('Regenerate scenes? This replaces all current scenes.')) loadScenes() }}
          disabled={loading}
          className="text-sm text-zinc-400 hover:text-white disabled:opacity-50"
        >
          ↻ Regenerate
        </button>
      </div>

      <div className="flex items-center gap-2">
        <span className="text-xs text-zinc-400">Aspect Ratio:</span>
        {(['16:9', '9:16', '1:1'] as const).map(ar => (
          <button
            key={ar}
            onClick={() => handleAspectRatio(ar)}
            className={`text-xs px-3 py-1 rounded border transition-colors ${
              aspectRatio === ar
                ? 'border-orange-500 text-orange-400'
                : 'border-zinc-700 text-zinc-400 hover:border-zinc-500'
            }`}
          >
            {ar}
          </button>
        ))}
      </div>

      {loading && <WizardSkeleton count={4} type="block" />}
      {error && (
        <div className="text-sm text-red-400 bg-red-950/30 border border-red-900 rounded p-3">
          {error}
          <button onClick={loadScenes} className="underline ml-2">Retry</button>
        </div>
      )}

      {!loading && !error && (
        <DndContext collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
          <SortableContext items={scenes.map(s => s.id)} strategy={verticalListSortingStrategy}>
            <div className="space-y-2">
              {scenes.map(scene => (
                <SortableScene
                  key={scene.id}
                  scene={scene}
                  projectId={project.id}
                  storyContext={storyContext}
                  sourceDocExcerpt={sourceDocExcerpt}
                  onUpdate={updated => setScenes(prev => prev.map(s => s.id === updated.id ? updated : s))}
                />
              ))}
            </div>
          </SortableContext>
        </DndContext>
      )}

      <button
        onClick={handleConfirm}
        disabled={scenes.length < 2 || !aspectRatio || confirming}
        className="bg-orange-500 hover:bg-orange-600 disabled:opacity-50 px-5 py-2 rounded font-medium text-sm"
      >
        {confirming ? 'Confirming...' : 'Confirm Scenes & Continue →'}
      </button>
    </div>
  )
}
