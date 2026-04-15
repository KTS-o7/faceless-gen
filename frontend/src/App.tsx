import { useState } from 'react'
import { Toaster } from 'sonner'
import { Layout } from './components/Layout'
import { ProjectsList } from './components/ProjectsList'
import { SettingsView } from './components/SettingsView'
import { AnglesStep } from './components/wizard/AnglesStep'
import { StoryStep } from './components/wizard/StoryStep'
import { ScenesStep } from './components/wizard/ScenesStep'
import { MusicStep } from './components/wizard/MusicStep'
import { GenerateStep } from './components/wizard/GenerateStep'
import { getProject } from './lib/api'
import type { ProjectDetail } from './types'

type TopView = 'projects' | 'settings'

const STAGE_TO_STEP: Record<string, number> = {
  angle_selection: 1,
  story_editing: 2,
  scene_editing: 3,
  music_selection: 4,
  generating: 5,
  done: 5,
  failed: 5,
}

export default function App() {
  const [topView, setTopView] = useState<TopView>('projects')
  const [activeProject, setActiveProject] = useState<ProjectDetail | null>(null)
  const [activeStep, setActiveStep] = useState<number | null>(null)

  function openProject(project: ProjectDetail) {
    setActiveProject(project)
    setActiveStep(STAGE_TO_STEP[project.stage] ?? 1)
    setTopView('projects')
  }

  async function advanceStep() {
    if (!activeProject) return
    const refreshed = await getProject(activeProject.id)
    setActiveProject(refreshed)
    setActiveStep(prev => (prev ?? 1) + 1)
  }

  function handleNavigate(view: TopView) {
    setTopView(view)
    if (view !== 'projects') setActiveProject(null)
  }

  function renderContent() {
    if (topView === 'settings') return <SettingsView />
    if (!activeProject) return <ProjectsList onOpenProject={openProject} />
    switch (activeStep) {
      case 1:
        return <AnglesStep project={activeProject} onContinue={advanceStep} onProjectUpdate={setActiveProject} />
      case 2:
        return <StoryStep project={activeProject} onContinue={advanceStep} />
      case 3:
        return <ScenesStep project={activeProject} onContinue={advanceStep} onProjectUpdate={setActiveProject} />
      case 4:
        return <MusicStep project={activeProject} onContinue={advanceStep} />
      case 5:
        return (
          <GenerateStep
            project={activeProject}
            onProjectUpdate={setActiveProject}
            onNewProject={() => {
              setActiveProject(null)
              setActiveStep(null)
            }}
          />
        )
      default:
        return (
          <div className="text-zinc-400 text-sm p-4">
            Step {activeStep} — coming soon
          </div>
        )
    }
  }

  return (
    <>
      <Toaster theme="dark" />
      <Layout
        activeTopView={topView}
        onNavigate={handleNavigate}
        activeProject={activeProject}
        activeStep={activeStep}
        onStepClick={setActiveStep}
      >
        {renderContent()}
      </Layout>
    </>
  )
}
