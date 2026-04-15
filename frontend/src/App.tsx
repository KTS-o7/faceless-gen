import { useState } from 'react'
import { Toaster } from 'sonner'
import { Layout } from './components/Layout'
import { GenerateForm } from './components/GenerateForm'
import { ProgressLog } from './components/ProgressLog'
import { VideoCard } from './components/VideoCard'
import { VideoHistory } from './components/VideoHistory'
import { SettingsView } from './components/SettingsView'
import { useGenerate } from './hooks/useGenerate'

type View = 'generate' | 'history' | 'settings'

export default function App() {
  const [view, setView] = useState<View>('generate')
  const { isGenerating, progressLog, currentJob, error, generate } = useGenerate()

  return (
    <>
      <Toaster theme="dark" />
      <Layout activeView={view} onNavigate={setView}>
        {view === 'generate' && (
          <div className="space-y-4">
            <GenerateForm onGenerate={generate} isGenerating={isGenerating} />
            {error && (
              <div className="text-sm text-red-400 bg-red-950/30 border border-red-900 rounded p-3">
                {error}
              </div>
            )}
            <ProgressLog logs={progressLog} isActive={isGenerating} />
            {currentJob && <VideoCard job={currentJob} />}
          </div>
        )}
        {view === 'history' && <VideoHistory />}
        {view === 'settings' && <SettingsView />}
      </Layout>
    </>
  )
}
