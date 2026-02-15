import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { getHostStats, getActiveScans, triggerScan, listScans } from '../api'
import SlotMachineLog from './SlotMachineLog'

export default function Dashboard() {
  const qc = useQueryClient()
  const stats = useQuery({ queryKey: ['stats'], queryFn: getHostStats })
  const active = useQuery({ queryKey: ['activeScans'], queryFn: getActiveScans })
  const recentScans = useQuery({ queryKey: ['scans'], queryFn: () => listScans() })

  const scanAll = useMutation({
    mutationFn: () => triggerScan(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['activeScans'] })
      qc.invalidateQueries({ queryKey: ['scans'] })
    },
  })

  const s = stats.data
  const isScanning = (active.data?.length ?? 0) > 0

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="font-display text-3xl font-black text-casino-gold">
            The House Floor
          </h2>
          <p className="text-gray-400 mt-1">Place your bets. Spin the scanner.</p>
        </div>
        <button
          className="btn-neon text-lg px-8 py-3"
          onClick={() => scanAll.mutate()}
          disabled={scanAll.isPending || isScanning}
        >
          {isScanning ? 'Spinning...' : 'Scan All Subnets'}
        </button>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <StatCard label="Total Hosts" value={s?.total_hosts ?? 0} icon="🃏" />
        <StatCard label="RDP Jackpots" value={s?.rdp_open ?? 0} icon="🎯" accent />
        <StatCard label="Subnets Played" value={s?.subnets_scanned ?? 0} icon="🎲" />
        <StatCard label="Total Spins" value={s?.total_scans ?? 0} icon="🎰" />
        <StatCard label="Announced" value={s?.announced ?? 0} icon="📢" />
      </div>

      {/* Active Scans */}
      {isScanning && (
        <div className="casino-card p-6">
          <h3 className="text-casino-neon font-bold text-sm uppercase tracking-widest mb-3">
            Active Spins
          </h3>
          <div className="space-y-2">
            {active.data?.map((scan) => (
              <div key={scan.id} className="flex items-center gap-3">
                <span className="badge badge-running">{scan.status}</span>
                <span className="text-gray-300 font-mono text-sm">
                  Scan #{scan.id} — {scan.subnet_cidr ?? `Subnet #${scan.subnet_id}`}
                  {scan.subnet_label && <span className="text-gray-500 ml-2">({scan.subnet_label})</span>}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Slot Machine Log */}
      <SlotMachineLog />

      {/* Recent Scans */}
      <div className="casino-card p-6">
        <h3 className="text-casino-gold font-bold text-sm uppercase tracking-widest mb-4">
          Recent Rolls
        </h3>
        {recentScans.data?.length === 0 ? (
          <p className="text-gray-500 italic">No scans yet. Hit "Scan All Subnets" to start.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Spin #</th>
                <th>Subnet</th>
                <th>Status</th>
                <th>Hosts</th>
                <th>RDP Hits</th>
                <th>VNC Hits</th>
                <th>Time</th>
              </tr>
            </thead>
            <tbody>
              {recentScans.data?.slice(0, 10).map((scan) => (
                <tr key={scan.id}>
                  <td className="text-casino-gold">#{scan.id}</td>
                  <td>
                    {scan.subnet_cidr ?? `#${scan.subnet_id}`}
                    {scan.subnet_label && <span className="text-gray-500 text-xs ml-1">({scan.subnet_label})</span>}
                  </td>
                  <td>
                    <span className={`badge badge-${scan.status}`}>{scan.status}</span>
                  </td>
                  <td>
                    {scan.hosts_found > 0 ? (
                      <Link to={`/hosts?subnet_id=${scan.subnet_id}`} className="text-white hover:text-casino-gold underline underline-offset-2 decoration-white/20 hover:decoration-casino-gold/50">
                        {scan.hosts_found}
                      </Link>
                    ) : scan.hosts_found}
                  </td>
                  <td>
                    {scan.rdp_found > 0 ? (
                      <Link to={`/hosts?subnet_id=${scan.subnet_id}&rdp_only=true`} className="text-casino-neon font-bold hover:text-casino-gold underline underline-offset-2 decoration-casino-neon/30 hover:decoration-casino-gold/50">
                        {scan.rdp_found}
                      </Link>
                    ) : scan.rdp_found}
                  </td>
                  <td>
                    {scan.vnc_found > 0 ? (
                      <Link to={`/hosts?subnet_id=${scan.subnet_id}&vnc_only=true`} className="text-purple-400 font-bold hover:text-casino-gold underline underline-offset-2 decoration-purple-400/30 hover:decoration-casino-gold/50">
                        {scan.vnc_found}
                      </Link>
                    ) : (scan.vnc_found ?? 0)}
                  </td>
                  <td className="text-gray-400 text-xs">
                    {scan.started_at ? new Date(scan.started_at).toLocaleString() : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

function StatCard({
  label,
  value,
  icon,
  accent,
}: {
  label: string
  value: number
  icon: string
  accent?: boolean
}) {
  return (
    <div className="casino-card p-5 text-center">
      <div className="text-2xl mb-1">{icon}</div>
      <div
        className={`text-3xl font-black font-mono ${
          accent ? 'text-casino-neon' : 'text-white'
        }`}
      >
        {value}
      </div>
      <div className="text-xs uppercase tracking-widest text-gray-400 mt-1">{label}</div>
    </div>
  )
}
