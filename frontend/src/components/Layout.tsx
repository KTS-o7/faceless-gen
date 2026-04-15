import type { ReactNode } from 'react'
import type { ProjectDetail } from '../types'

type TopView = 'projects' | 'settings'

interface LayoutProps {
  children: ReactNode
  activeTopView: TopView
  onNavigate: (view: TopView) => void
  activeProject: ProjectDetail | null
  activeStep: number | null
  onStepClick: (step: number) => void
}

const STAGE_TO_STEP: Record<string, number> = {
  angle_selection: 1, story_editing: 2, scene_editing: 3,
  music_selection: 4, generating: 5, done: 5, failed: 5,
}

const STEP_LABELS = ['Angles', 'Story', 'Scenes', 'Music', 'Generate']

export function Layout({ children, activeTopView, onNavigate, activeProject, activeStep, onStepClick }: LayoutProps) {
  const maxStep = activeProject ? (STAGE_TO_STEP[activeProject.stage] ?? 1) : 0
  return (
    <div className="min-h-screen bg-zinc-950 text-white flex">
      {/* Sidebar */}
      <aside className="w-52 border-r border-zinc-800 flex flex-col pt-4 px-2 flex-shrink-0">
        <div className="px-2 mb-6">
          <h1 className="text-base font-bold text-orange-400">⚡ Faceless-Gen</h1>
          <p className="text-xs text-zinc-500">Local AI Video Studio</p>
        </div>
        <nav className="space-y-0.5">
          {(['projects', 'settings'] as TopView[]).map((v) => (
            <button key={v} onClick={() => onNavigate(v)}
              className={`w-full text-left px-3 py-2 rounded text-sm capitalize transition-colors ${activeTopView === v && !activeProject ? 'bg-zinc-800 text-white' : 'text-zinc-400 hover:text-white'}`}>
              {v === 'projects' ? '📁 Projects' : '⚙️ Settings'}
            </button>
          ))}
        </nav>
        {activeProject && (
          <div className="mt-4 border-t border-zinc-800 pt-4">
            <p className="text-xs text-zinc-500 px-3 mb-2 truncate">{activeProject.name}</p>
            {STEP_LABELS.map((label, i) => {
              const step = i + 1
              const isComplete = step < maxStep
              const isActive = step === activeStep
              const isLocked = step > maxStep
              return (
                <button key={step} onClick={() => !isLocked && onStepClick(step)}
                  disabled={isLocked}
                  className={`w-full text-left px-3 py-2 rounded text-sm flex items-center gap-2 transition-colors ${isActive ? 'bg-zinc-800 text-white' : isLocked ? 'text-zinc-600 cursor-not-allowed' : 'text-zinc-400 hover:text-white'}`}>
                  <span className="text-xs">{isComplete ? '✅' : isActive ? '🔵' : isLocked ? '🔒' : '⚪'}</span>
                  {step}. {label}
                </button>
              )
            })}
          </div>
        )}
      </aside>
      {/* Main */}
      <main className="flex-1 overflow-y-auto">
        <div className="max-w-3xl mx-auto px-6 py-6">{children}</div>
      </main>
    </div>
  )
}
