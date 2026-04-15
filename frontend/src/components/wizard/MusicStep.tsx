import { useState, useEffect, useRef } from 'react'
import type { ProjectDetail } from '../../types'

interface Track {
  filename: string
  title: string
  mood: string
  duration_seconds: number
}

interface Props {
  project: ProjectDetail
  onContinue: () => void
}

function formatDuration(secs: number): string {
  const m = Math.floor(secs / 60)
  const s = secs % 60
  return `${m}:${s.toString().padStart(2, '0')}`
}

const MOOD_COLORS: Record<string, string> = {
  calm: 'bg-blue-500/20 text-blue-400',
  upbeat: 'bg-yellow-500/20 text-yellow-400',
  cinematic: 'bg-purple-500/20 text-purple-400',
  ambient: 'bg-teal-500/20 text-teal-400',
  dramatic: 'bg-red-500/20 text-red-400',
}

export function MusicStep({ project, onContinue }: Props) {
  const [tracks, setTracks] = useState<Track[]>([])
  const [selected, setSelected] = useState<string | null>(project.music_track)
  const [playing, setPlaying] = useState<string | null>(null)
  const audioRef = useRef<HTMLAudioElement | null>(null)

  useEffect(() => {
    fetch('/api/music/tracks')
      .then(r => r.json())
      .then(setTracks)
      .catch(() => setTracks([]))
  }, [])

  async function selectTrack(filename: string | null) {
    setSelected(filename)
    await fetch(`/api/projects/${project.id}/music/select`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ track_filename: filename }),
    })
  }

  function togglePlay(filename: string) {
    if (playing === filename) {
      audioRef.current?.pause()
      setPlaying(null)
    } else {
      if (audioRef.current) audioRef.current.pause()
      const audio = new Audio(`/assets/music/${filename}`)
      audio.onended = () => setPlaying(null)
      audio.play().catch(() => {})
      audioRef.current = audio
      setPlaying(filename)
    }
  }

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">Select Music</h2>

      {/* No music option */}
      <div
        onClick={() => selectTrack(null)}
        className={`bg-zinc-900 border rounded-lg p-3 cursor-pointer transition-colors ${
          !selected ? 'border-orange-500' : 'border-zinc-800 hover:border-zinc-600'
        }`}
      >
        <p className="text-sm font-medium">No Music</p>
        <p className="text-xs text-zinc-500 mt-0.5">Generate without background music</p>
      </div>

      {tracks.length === 0 && (
        <p className="text-xs text-zinc-500">
          No music tracks found. Add MP3 files to backend/assets/music/ and update tracks.json.
        </p>
      )}

      {tracks.map(track => (
        <div
          key={track.filename}
          onClick={() => selectTrack(track.filename)}
          className={`bg-zinc-900 border rounded-lg p-3 cursor-pointer transition-colors ${
            selected === track.filename
              ? 'border-orange-500'
              : 'border-zinc-800 hover:border-zinc-600'
          }`}
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <button
                onClick={e => {
                  e.stopPropagation()
                  togglePlay(track.filename)
                }}
                className="text-zinc-400 hover:text-white w-6 text-center"
              >
                {playing === track.filename ? '⏸' : '▶'}
              </button>
              <div>
                <p className="text-sm font-medium">{track.title}</p>
                <p className="text-xs text-zinc-500">{formatDuration(track.duration_seconds)}</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <span
                className={`text-xs px-2 py-0.5 rounded-full ${
                  MOOD_COLORS[track.mood] ?? 'bg-zinc-700 text-zinc-400'
                }`}
              >
                {track.mood}
              </span>
              {selected === track.filename && (
                <span className="text-orange-400 text-sm">✓</span>
              )}
            </div>
          </div>
        </div>
      ))}

      <button
        onClick={onContinue}
        className="bg-orange-500 hover:bg-orange-600 px-5 py-2 rounded font-medium text-sm"
      >
        Continue to Generate →
      </button>
    </div>
  )
}
