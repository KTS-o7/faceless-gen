interface Props { count?: number; type?: 'card' | 'block' }

export function WizardSkeleton({ count = 3, type = 'card' }: Props) {
  return (
    <div className="space-y-3">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className={`bg-zinc-800 rounded-lg animate-pulse ${type === 'card' ? 'h-32' : 'h-20'}`} />
      ))}
    </div>
  )
}
