import { useState, useEffect } from 'react'
import { generateAngles, chooseAngle } from '../../lib/api'
import { WizardSkeleton } from './WizardSkeleton'
import type { ProjectDetail, AngleResponse } from '../../types'

interface Props {
  project: ProjectDetail
  onContinue: () => void
  onProjectUpdate: (p: ProjectDetail) => void
}

export function AnglesStep({ project, onContinue }: Props) {
  const [angles, setAngles] = useState<AngleResponse[]>(project.angles)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [choosing, setChoosing] = useState<string | null>(null)

  useEffect(() => {
    if (angles.length === 0) loadAngles()
  }, [])

  async function loadAngles() {
    setLoading(true); setError(null)
    try { setAngles(await generateAngles(project.id)) }
    catch (e) { setError(e instanceof Error && e.message.includes('422') ? 'The AI returned an unexpected response. Try regenerating.' : String(e)) }
    finally { setLoading(false) }
  }

  async function handleChoose(angleId: string) {
    setChoosing(angleId)
    try {
      await chooseAngle(project.id, angleId)
      setAngles(prev => prev.map(a => ({ ...a, chosen: a.id === angleId })))
    } finally { setChoosing(null) }
  }

  const chosen = angles.find(a => a.chosen)

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Choose an Angle</h2>
        <button onClick={loadAngles} disabled={loading}
          className="text-sm text-zinc-400 hover:text-white disabled:opacity-50">
          ↻ Regenerate
        </button>
      </div>

      {loading && <WizardSkeleton count={3} type="card" />}
      {error && (
        <div className="text-sm text-red-400 bg-red-950/30 border border-red-900 rounded p-3">
          {error} <button onClick={loadAngles} className="underline ml-2">Retry</button>
        </div>
      )}

      {!loading && !error && (
        <div className="grid gap-3">
          {angles.map(angle => (
            <div key={angle.id}
              className={`bg-zinc-900 border rounded-lg p-4 transition-colors ${angle.chosen ? 'border-green-500' : 'border-zinc-800'}`}>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="font-medium text-sm">{angle.chosen && '✅ '}{angle.title}</p>
                  <p className="text-sm text-zinc-400 mt-1">{angle.pitch}</p>
                </div>
                <button onClick={() => handleChoose(angle.id)}
                  disabled={choosing === angle.id || angle.chosen}
                  className={`flex-shrink-0 text-xs px-3 py-1.5 rounded font-medium transition-colors ${angle.chosen ? 'bg-green-500/20 text-green-400' : 'bg-zinc-700 hover:bg-zinc-600'} disabled:opacity-60`}>
                  {choosing === angle.id ? '...' : angle.chosen ? 'Chosen' : 'Choose'}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {chosen && (
        <div className="pt-2">
          <button onClick={onContinue}
            className="bg-orange-500 hover:bg-orange-600 px-5 py-2 rounded font-medium text-sm">
            Continue to Story →
          </button>
        </div>
      )}
    </div>
  )
}
