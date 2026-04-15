import { useState } from 'react'

export function SettingsView() {
  const [model, setModel] = useState(() => localStorage.getItem('model') ?? 'gpt-4o-mini')
  const [voiceId, setVoiceId] = useState(() => localStorage.getItem('voiceId') ?? '21m00Tcm4TlvDq8ikWAM')

  function save() {
    localStorage.setItem('model', model)
    localStorage.setItem('voiceId', voiceId)
  }

  return (
    <div className="max-w-md space-y-6">
      <h2 className="text-lg font-semibold">Settings</h2>
      <div className="space-y-4">
        <div>
          <label className="block text-sm text-zinc-400 mb-1">LLM Model</label>
          <input
            value={model}
            onChange={(e) => setModel(e.target.value)}
            className="w-full bg-zinc-900 border border-zinc-700 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-orange-500"
          />
        </div>
        <div>
          <label className="block text-sm text-zinc-400 mb-1">ElevenLabs Voice ID</label>
          <input
            value={voiceId}
            onChange={(e) => setVoiceId(e.target.value)}
            className="w-full bg-zinc-900 border border-zinc-700 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-orange-500"
          />
        </div>
        <p className="text-xs text-zinc-600">These are UI preferences only. To change API keys, edit <code>.env</code> and restart the server.</p>
        <button
          onClick={save}
          className="bg-orange-500 hover:bg-orange-600 px-4 py-2 rounded text-sm font-medium transition-colors"
        >
          Save Preferences
        </button>
      </div>
    </div>
  )
}
