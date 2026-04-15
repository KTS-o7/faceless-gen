import type { Job } from '../types'
import { motion } from 'framer-motion'

const statusColors: Record<string, string> = {
  pending: 'bg-yellow-500/20 text-yellow-400',
  running: 'bg-blue-500/20 text-blue-400',
  done: 'bg-green-500/20 text-green-400',
  failed: 'bg-red-500/20 text-red-400',
}

interface Props { job: Job }

export function VideoCard({ job }: Props) {
  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="bg-zinc-900 border border-zinc-800 rounded-lg p-4 space-y-3"
    >
      <div className="flex items-start justify-between gap-2">
        <p className="text-sm text-zinc-300 line-clamp-2">{job.user_prompt}</p>
        <span className={`text-xs px-2 py-0.5 rounded-full whitespace-nowrap ${statusColors[job.status]}`}>
          {job.status}
        </span>
      </div>
      {job.scene_thumbnails.length > 0 && (
        <div className="flex gap-2 overflow-x-auto pb-1">
          {job.scene_thumbnails.map((thumb, i) => (
            <img
              key={i}
              src={`/outputs/${job.job_id}/${thumb}`}
              alt={`Scene ${i + 1}`}
              className="h-16 w-28 object-cover rounded flex-shrink-0"
              onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }}
            />
          ))}
        </div>
      )}
      {job.status === 'done' && job.final_output && (
        <video
          controls
          src={`/outputs/${job.job_id}/final.mp4`}
          className="w-full rounded"
        />
      )}
      {job.error && (
        <pre className="text-xs text-red-400 bg-red-950/30 border border-red-900 rounded p-2 overflow-auto">
          {job.error}
        </pre>
      )}
    </motion.div>
  )
}
