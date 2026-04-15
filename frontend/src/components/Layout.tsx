import type { ReactNode } from 'react'

type View = 'generate' | 'history' | 'settings'

interface LayoutProps {
  children: ReactNode
  activeView: View
  onNavigate: (view: View) => void
}

export function Layout({ children, activeView, onNavigate }: LayoutProps) {
  const navItems: { id: View; label: string }[] = [
    { id: 'generate', label: 'Generate' },
    { id: 'history', label: 'History' },
    { id: 'settings', label: 'Settings' },
  ]
  return (
    <div className="min-h-screen bg-zinc-950 text-white">
      <header className="border-b border-zinc-800 px-4 py-3">
        <div className="max-w-4xl mx-auto flex items-center justify-between">
          <div>
            <h1 className="text-lg font-bold text-orange-400">⚡ Faceless-Gen</h1>
            <p className="text-xs text-zinc-400">Local AI Video Studio</p>
          </div>
          <nav className="flex gap-1">
            {navItems.map((item) => (
              <button
                key={item.id}
                onClick={() => onNavigate(item.id)}
                className={`px-3 py-1.5 rounded text-sm transition-colors ${
                  activeView === item.id
                    ? 'bg-zinc-800 text-white'
                    : 'text-zinc-400 hover:text-white'
                }`}
              >
                {item.label}
              </button>
            ))}
          </nav>
        </div>
      </header>
      <main className="max-w-4xl mx-auto px-4 py-6">{children}</main>
    </div>
  )
}
