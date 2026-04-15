import { useHistory } from '../hooks/useHistory'
import { VideoCard } from './VideoCard'

export function VideoHistory() {
  const { jobs, loading, refresh } = useHistory()

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold">History</h2>
        <button
          onClick={refresh}
          className="text-sm text-zinc-400 hover:text-white transition-colors"
        >
          ↻ Refresh
        </button>
      </div>
      {loading ? (
        <p className="text-zinc-500 text-sm">Loading...</p>
      ) : jobs.length === 0 ? (
        <div className="text-center py-16 text-zinc-600">
          <p className="text-4xl mb-2">🎬</p>
          <p className="text-sm">No videos generated yet.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {jobs.map((job) => <VideoCard key={job.job_id} job={job} />)}
        </div>
      )}
    </div>
  )
}
