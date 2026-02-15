import { NavLink } from 'react-router-dom'
import type { ReactNode } from 'react'

const links = [
  { to: '/', label: 'Dashboard' },
  { to: '/subnets', label: 'Subnets' },
  { to: '/hosts', label: 'Hosts' },
  { to: '/scans', label: 'Scan Log' },
]

export default function Layout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen">
      <nav className="border-b border-casino-gold/20 bg-black/40 backdrop-blur-sm">
        <div className="max-w-7xl mx-auto px-4 flex items-center h-16 gap-8">
          <div className="flex items-center gap-3">
            <span className="text-3xl" role="img" aria-label="dice">
              🎰
            </span>
            <h1 className="font-display text-2xl font-black text-casino-gold tracking-wide">
              RDP LOTTERY
            </h1>
          </div>
          <div className="flex gap-1">
            {links.map((l) => (
              <NavLink
                key={l.to}
                to={l.to}
                end={l.to === '/'}
                className={({ isActive }) =>
                  `px-4 py-2 rounded-lg text-sm font-semibold uppercase tracking-wider transition-all ${
                    isActive
                      ? 'bg-casino-gold/20 text-casino-gold border border-casino-gold/40'
                      : 'text-gray-400 hover:text-casino-gold-bright hover:bg-white/5'
                  }`
                }
              >
                {l.label}
              </NavLink>
            ))}
          </div>
        </div>
      </nav>
      <main className="max-w-7xl mx-auto px-4 py-8">{children}</main>
    </div>
  )
}
