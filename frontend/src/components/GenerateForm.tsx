import { useState } from 'react'

interface Props {
  onGenerate: (prompt: string) => void
  isGenerating: boolean
}

export function GenerateForm({ onGenerate, isGenerating }: Props) {
  const [prompt, setPrompt] = useState('')

  return (
    <div className="space-y-3">
      <textarea
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        disabled={isGenerating}
        placeholder="Describe your video..."
        rows={4}
        className="w-full bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-white placeholder-zinc-500 resize-y disabled:opacity-50 focus:outline-none focus:border-orange-500"
      />
      <div className="flex items-center gap-3">
        <select className="bg-zinc-900 border border-zinc-700 rounded px-2 py-1.5 text-sm text-white">
          <option value="gpt-4o-mini">gpt-4o-mini</option>
          <option value="gpt-4o">gpt-4o</option>
          <option value="claude-3-5-sonnet-20241022">claude-3-5-sonnet</option>
          <option value="gemini-2.0-flash">gemini-2.0-flash</option>
        </select>
        <button
          onClick={() => onGenerate(prompt)}
          disabled={!prompt.trim() || isGenerating}
          className="flex items-center gap-2 bg-orange-500 hover:bg-orange-600 disabled:opacity-50 disabled:cursor-not-allowed px-4 py-1.5 rounded text-sm font-medium transition-colors"
        >
          {isGenerating ? (
            <><span className="animate-spin">⟳</span> Generating...</>
          ) : (
            <>✦ Generate</>
          )}
        </button>
      </div>
    </div>
  )
}
