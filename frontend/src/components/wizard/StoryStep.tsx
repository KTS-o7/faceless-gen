import { useState, useEffect } from 'react'
import { DndContext, closestCenter, type DragEndEvent } from '@dnd-kit/core'
import { SortableContext, verticalListSortingStrategy, useSortable, arrayMove } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { generateStory, reorderStory, updateStoryBlock, deleteStoryBlock, confirmStory } from '../../lib/api'
import { WizardSkeleton } from './WizardSkeleton'
import type { ProjectDetail, StoryBlockResponse } from '../../types'

function SortableBlock({ block, projectId, onDelete, onUpdate }: {
  block: StoryBlockResponse
  projectId: string
  onDelete: (id: string) => void
  onUpdate: (id: string, content: string) => void
}) {
  const { attributes, listeners, setNodeRef, transform, transition } = useSortable({ id: block.id })
  const [content, setContent] = useState(block.content)

  async function handleBlur() {
    if (content !== block.content) {
      await updateStoryBlock(projectId, block.id, content)
      onUpdate(block.id, content)
    }
  }

  return (
    <div ref={setNodeRef} style={{ transform: CSS.Transform.toString(transform), transition }}
      className="bg-zinc-900 border border-zinc-800 rounded-lg p-3 flex gap-3">
      <button {...attributes} {...listeners} className="text-zinc-600 hover:text-zinc-400 cursor-grab mt-1 text-lg leading-none">⠿</button>
      <div className="flex-1">
        <textarea value={content} onChange={e => setContent(e.target.value)} onBlur={handleBlur}
          rows={3}
          className="w-full bg-transparent text-sm text-zinc-200 resize-none focus:outline-none" />
      </div>
      <button onClick={() => onDelete(block.id)} className="text-zinc-600 hover:text-red-400 text-sm mt-1">🗑</button>
    </div>
  )
}

interface Props {
  project: ProjectDetail
  onContinue: () => void
}

export function StoryStep({ project, onContinue }: Props) {
  const [blocks, setBlocks] = useState<StoryBlockResponse[]>(project.story_blocks)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [confirming, setConfirming] = useState(false)

  useEffect(() => {
    if (blocks.length === 0) loadStory()
  }, [])

  async function loadStory() {
    setLoading(true); setError(null)
    try { setBlocks(await generateStory(project.id)) }
    catch (e) { setError(e instanceof Error && e.message.includes('422') ? 'The AI returned an unexpected response. Try regenerating.' : String(e)) }
    finally { setLoading(false) }
  }

  async function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event
    if (!over || active.id === over.id) return
    const oldIndex = blocks.findIndex(b => b.id === active.id)
    const newIndex = blocks.findIndex(b => b.id === over.id)
    const reordered = arrayMove(blocks, oldIndex, newIndex)
    setBlocks(reordered)
    await reorderStory(project.id, reordered.map(b => b.id))
  }

  async function handleDelete(id: string) {
    setBlocks(prev => prev.filter(b => b.id !== id))
    await deleteStoryBlock(project.id, id)
  }

  async function handleConfirm() {
    setConfirming(true)
    try { await confirmStory(project.id); onContinue() }
    finally { setConfirming(false) }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Edit Story</h2>
        <button onClick={() => { if (confirm('Regenerate? This will replace all current blocks.')) loadStory() }}
          disabled={loading} className="text-sm text-zinc-400 hover:text-white disabled:opacity-50">
          ↻ Regenerate
        </button>
      </div>

      {loading && <WizardSkeleton count={4} type="block" />}
      {error && (
        <div className="text-sm text-red-400 bg-red-950/30 border border-red-900 rounded p-3">
          {error} <button onClick={loadStory} className="underline ml-2">Retry</button>
        </div>
      )}

      {!loading && !error && (
        <DndContext collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
          <SortableContext items={blocks.map(b => b.id)} strategy={verticalListSortingStrategy}>
            <div className="space-y-2">
              {blocks.map((block, i) => (
                <div key={block.id}>
                  <p className="text-xs text-zinc-600 mb-1">Block {i + 1}</p>
                  <SortableBlock block={block} projectId={project.id} onDelete={handleDelete}
                    onUpdate={(id, content) => setBlocks(prev => prev.map(b => b.id === id ? { ...b, content } : b))} />
                </div>
              ))}
            </div>
          </SortableContext>
        </DndContext>
      )}

      <button onClick={handleConfirm} disabled={blocks.length < 2 || confirming}
        className="bg-orange-500 hover:bg-orange-600 disabled:opacity-50 px-5 py-2 rounded font-medium text-sm">
        {confirming ? 'Confirming...' : 'Confirm Story & Continue →'}
      </button>
    </div>
  )
}
