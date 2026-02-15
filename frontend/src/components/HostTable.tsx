import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router-dom'
import { listHosts, listSubnets } from '../api'

export default function HostTable() {
  const [searchParams] = useSearchParams()
  const [rdpOnly, setRdpOnly] = useState(searchParams.get('rdp_only') === 'true')
  const [vncOnly, setVncOnly] = useState(searchParams.get('vnc_only') === 'true')
  const initSubnet = searchParams.get('subnet_id')
  const [subnetId, setSubnetId] = useState<number | undefined>(initSubnet ? Number(initSubnet) : undefined)
  const [sortKey, setSortKey] = useState<'ip' | 'last_seen_at' | 'rdp_open'>('last_seen_at')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')

  const hosts = useQuery({
    queryKey: ['hosts', rdpOnly, vncOnly, subnetId],
    queryFn: () => listHosts({ rdpOnly, vncOnly, subnetId }),
  })

  const subnets = useQuery({ queryKey: ['subnets'], queryFn: listSubnets })

  const sorted = [...(hosts.data ?? [])].sort((a, b) => {
    const mul = sortDir === 'asc' ? 1 : -1
    if (sortKey === 'ip') {
      const aParts = a.ip.split('.').map(Number)
      const bParts = b.ip.split('.').map(Number)
      for (let i = 0; i < 4; i++) {
        if (aParts[i] !== bParts[i]) return (aParts[i] - bParts[i]) * mul
      }
      return 0
    }
    if (sortKey === 'rdp_open') return (a.rdp_open - b.rdp_open) * mul
    return (a[sortKey] > b[sortKey] ? 1 : -1) * mul
  })

  const toggleSort = (key: typeof sortKey) => {
    if (sortKey === key) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    else {
      setSortKey(key)
      setSortDir('desc')
    }
  }

  return (
    <div className="space-y-8">
      <div>
        <h2 className="font-display text-3xl font-black text-casino-gold">
          The Winners Circle
        </h2>
        <p className="text-gray-400 mt-1">All discovered hosts across your subnets.</p>
      </div>

      {/* Filters */}
      <div className="casino-card p-4 flex gap-4 items-center flex-wrap">
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={rdpOnly}
            onChange={(e) => setRdpOnly(e.target.checked)}
            className="w-4 h-4 accent-casino-gold"
          />
          <span className="text-sm text-gray-300 uppercase tracking-wider">RDP Only</span>
        </label>
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={vncOnly}
            onChange={(e) => setVncOnly(e.target.checked)}
            className="w-4 h-4 accent-purple-500"
          />
          <span className="text-sm text-gray-300 uppercase tracking-wider">VNC Only</span>
        </label>
        <select
          value={subnetId ?? ''}
          onChange={(e) => setSubnetId(e.target.value ? Number(e.target.value) : undefined)}
        >
          <option value="">All Subnets</option>
          {subnets.data?.map((s) => (
            <option key={s.id} value={s.id}>
              {s.cidr} {s.label ? `(${s.label})` : ''}
            </option>
          ))}
        </select>
      </div>

      {/* Table */}
      <div className="casino-card p-6 overflow-x-auto">
        {sorted.length === 0 ? (
          <p className="text-gray-500 italic">No hosts found. Run a scan first.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <SortTh label="IP Address" sortKey="ip" current={sortKey} dir={sortDir} onClick={toggleSort} />
                <th>Hostname</th>
                <SortTh label="RDP" sortKey="rdp_open" current={sortKey} dir={sortDir} onClick={toggleSort} />
                <th>VNC</th>
                <th>NLA</th>
                <th>Domain</th>
                <th>Ports</th>
                <th>Country</th>
                <th>Type</th>
                <SortTh label="Last Seen" sortKey="last_seen_at" current={sortKey} dir={sortDir} onClick={toggleSort} />
                <th></th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((host) => (
                <tr key={host.id}>
                  <td className="text-white font-semibold">{host.ip}</td>
                  <td className="text-gray-300">{host.hostname || '—'}</td>
                  <td>
                    {host.rdp_open ? (
                      <span className="text-casino-neon font-bold">HIT</span>
                    ) : (
                      <span className="text-gray-600">—</span>
                    )}
                  </td>
                  <td>
                    {host.vnc_open ? (
                      <span className="text-purple-400 font-bold">VNC</span>
                    ) : (
                      <span className="text-gray-600">—</span>
                    )}
                    {host.vnc_open && host.vnc_auth_required === 0 ? (
                      <span className="ml-1 text-xs text-purple-300">OPEN</span>
                    ) : null}
                  </td>
                  <td>
                    {host.nla_required === null ? (
                      <span className="text-gray-600">—</span>
                    ) : host.nla_required === 0 ? (
                      <span className="badge badge-running">NO NLA</span>
                    ) : (
                      <span className="badge badge-pending">NLA</span>
                    )}
                  </td>
                  <td className="text-gray-300">{host.domain || '—'}</td>
                  <td className="text-gray-400">{host.all_ports?.length ?? 0}</td>
                  <td className="text-gray-400 text-xs">{host.country_code || '—'}</td>
                  <td>
                    <IpTypeBadge type={host.ip_type} />
                  </td>
                  <td className="text-gray-400 text-xs">
                    {new Date(host.last_seen_at).toLocaleDateString()}
                  </td>
                  <td>
                    <Link
                      to={`/hosts/${host.id}`}
                      className="text-casino-gold hover:text-casino-gold-bright text-sm font-semibold"
                    >
                      Details
                    </Link>
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

function IpTypeBadge({ type }: { type: string }) {
  if (!type) return <span className="text-gray-600">—</span>
  const colors: Record<string, string> = {
    Datacenter: 'bg-red-600/20 text-red-400 border-red-500/30',
    Residential: 'bg-green-600/20 text-green-400 border-green-500/30',
    Private: 'bg-gray-600/20 text-gray-400 border-gray-500/30',
    Mobile: 'bg-blue-600/20 text-blue-400 border-blue-500/30',
  }
  const cls = colors[type] ?? 'bg-gray-600/20 text-gray-400 border-gray-500/30'
  return (
    <span className={`text-xs font-bold px-2 py-0.5 rounded border ${cls}`}>
      {type.toUpperCase()}
    </span>
  )
}

function SortTh({
  label,
  sortKey,
  current,
  dir,
  onClick,
}: {
  label: string
  sortKey: string
  current: string
  dir: string
  onClick: (key: any) => void
}) {
  const active = current === sortKey
  return (
    <th className="cursor-pointer select-none" onClick={() => onClick(sortKey)}>
      {label} {active ? (dir === 'asc' ? '▲' : '▼') : ''}
    </th>
  )
}
