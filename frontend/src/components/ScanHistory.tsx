import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { listScans, triggerScan } from '../api'

export default function ScanHistory() {
  const qc = useQueryClient()
  const scans = useQuery({ queryKey: ['scans'], queryFn: () => listScans() })

  const rescan = useMutation({
    mutationFn: (subnetId: number) => triggerScan(subnetId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['scans'] })
      qc.invalidateQueries({ queryKey: ['activeScans'] })
    },
  })

  return (
    <div className="space-y-8">
      <div>
        <h2 className="font-display text-3xl font-black text-casino-gold">
          The Ledger
        </h2>
        <p className="text-gray-400 mt-1">Complete scan history.</p>
      </div>

      <div className="casino-card p-6 overflow-x-auto">
        {scans.data?.length === 0 ? (
          <p className="text-gray-500 italic">No scans yet.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Spin #</th>
                <th>Subnet</th>
                <th>Status</th>
                <th>Hosts Found</th>
                <th>RDP Hits</th>
                <th>VNC Hits</th>
                <th>Started</th>
                <th>Finished</th>
                <th>Error</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {scans.data?.map((scan) => {
                const duration = scan.started_at && scan.finished_at
                  ? formatDuration(new Date(scan.finished_at).getTime() - new Date(scan.started_at).getTime())
                  : null

                return (
                  <tr key={scan.id}>
                    <td className="text-casino-gold font-bold">#{scan.id}</td>
                    <td>
                      <span className="text-white">{scan.subnet_cidr ?? `#${scan.subnet_id}`}</span>
                      {scan.subnet_label && (
                        <span className="text-gray-500 text-xs ml-2">{scan.subnet_label}</span>
                      )}
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
                    <td className="text-gray-400 text-xs">
                      {scan.finished_at ? (
                        <>
                          {new Date(scan.finished_at).toLocaleString()}
                          {duration && <span className="text-gray-600 ml-1">({duration})</span>}
                        </>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td className="text-casino-red-bright text-xs max-w-48 truncate">
                      {scan.error || ''}
                    </td>
                    <td>
                      <button
                        className="btn-neon btn-sm"
                        onClick={() => rescan.mutate(scan.subnet_id)}
                        disabled={rescan.isPending || scan.status === 'running' || scan.status === 'pending'}
                      >
                        Re-scan
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

function formatDuration(ms: number): string {
  const seconds = Math.floor(ms / 1000)
  if (seconds < 60) return `${seconds}s`
  const minutes = Math.floor(seconds / 60)
  const remaining = seconds % 60
  return `${minutes}m ${remaining}s`
}
