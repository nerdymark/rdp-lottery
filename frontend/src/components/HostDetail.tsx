import { useParams, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getHost, triggerScan, reannounceHost } from '../api'

export default function HostDetail() {
  const { id } = useParams<{ id: string }>()
  const host = useQuery({
    queryKey: ['host', id],
    queryFn: () => getHost(Number(id)),
    enabled: !!id,
  })

  const queryClient = useQueryClient()
  const rescan = useMutation({
    mutationFn: (subnetId: number) => triggerScan(subnetId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['host', id] })
    },
  })

  const reannounce = useMutation({
    mutationFn: () => reannounceHost(Number(id)),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['host', id] })
    },
  })

  if (host.isLoading) return <p className="text-gray-400">Loading...</p>
  if (!host.data) return <p className="text-casino-red-bright">Host not found.</p>

  const h = host.data
  const webPorts = new Set((h.web_screenshots || []).map((ws) => ws.port))

  return (
    <div className="space-y-8">
      <div className="flex items-center gap-4">
        <Link to="/hosts" className="text-casino-gold hover:text-casino-gold-bright">
          ← Back
        </Link>
        <h2 className="font-display text-3xl font-black text-casino-gold">{h.ip}</h2>
        {h.rdp_open ? (
          <span className="badge badge-running">RDP JACKPOT</span>
        ) : (
          <span className="badge badge-pending">No RDP</span>
        )}
        {h.vnc_open ? (
          <span className="badge" style={{ background: 'rgba(168,85,247,0.2)', color: '#c084fc', borderColor: 'rgba(168,85,247,0.3)' }}>VNC OPEN</span>
        ) : null}
        {h.vnc_auth_required === 0 && (
          <span className="badge badge-running">VNC NO AUTH</span>
        )}
        {h.vnc_auth_required === 1 && (
          <span className="badge badge-pending">VNC AUTH</span>
        )}
        {h.nla_required === 0 && (
          <span className="badge badge-running">NO NLA</span>
        )}
        {h.nla_required === 1 && (
          <span className="badge badge-pending">NLA</span>
        )}
        <div className="ml-auto flex gap-2">
          {(h.screenshot_path || h.vnc_screenshot_path) && (
            <button
              className="btn-neon text-sm"
              disabled={reannounce.isPending}
              onClick={() => reannounce.mutate()}
            >
              {reannounce.isPending ? 'Announcing...' : 'Re-announce'}
            </button>
          )}
          <button
            className="btn-neon text-sm"
            disabled={rescan.isPending}
            onClick={() => rescan.mutate(h.subnet_id)}
          >
            {rescan.isPending ? 'Scanning...' : 'Re-scan'}
          </button>
        </div>
      </div>

      {/* Host info cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="casino-card p-6 space-y-4">
          <h3 className="text-casino-gold font-bold text-sm uppercase tracking-widest">
            Identity
          </h3>
          <InfoRow label="Hostname" value={h.hostname} />
          <InfoRow label="NetBIOS Name" value={h.netbios_name} />
          <InfoRow label="Domain" value={h.domain} />
          <InfoRow label="MAC Address" value={h.mac_address} />
          {h.os_guess && <InfoRow label="OS Guess" value={h.os_guess} />}
        </div>

        <div className="casino-card p-6 space-y-4">
          <h3 className="text-casino-gold font-bold text-sm uppercase tracking-widest">
            Metadata
          </h3>
          <InfoRow label="First Seen" value={new Date(h.first_seen_at).toLocaleString()} />
          <InfoRow label="Last Seen" value={new Date(h.last_seen_at).toLocaleString()} />
          <InfoRow label="Announced" value={h.announced ? 'Yes' : 'No'} />
          <InfoRow label="NLA Required" value={h.nla_required === null ? 'Unchecked' : h.nla_required ? 'Yes' : 'No'} />
          {h.vnc_open ? <InfoRow label="VNC Auth" value={h.vnc_auth_required === null ? 'Unchecked' : h.vnc_auth_required ? 'Required' : 'None'} /> : null}
          {h.vnc_desktop_name ? <InfoRow label="VNC Desktop" value={h.vnc_desktop_name} /> : null}
          <InfoRow label="Scan ID" value={String(h.scan_id)} />
          <InfoRow label="Subnet ID" value={String(h.subnet_id)} />
        </div>
      </div>

      {/* Network Intelligence */}
      {(h.asn || h.isp || h.country || h.ip_type || h.reverse_dns) && (
        <div className="casino-card p-6 space-y-4">
          <h3 className="text-casino-gold font-bold text-sm uppercase tracking-widest">
            Network Intelligence
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-0">
            <InfoRow label="ASN" value={h.asn} />
            <InfoRow label="ISP" value={h.isp} />
            <InfoRow label="Organization" value={h.org} />
            <InfoRow label="Country" value={h.country} />
            <InfoRow label="City" value={h.city} />
            <InfoRow label="Reverse DNS" value={h.reverse_dns} />
            <InfoRow label="Coordinates" value={h.latitude != null && h.longitude != null ? `${h.latitude}, ${h.longitude}` : ''} />
            <div className="flex justify-between border-b border-white/5 pb-2">
              <span className="text-gray-400 text-sm uppercase tracking-wider">IP Type</span>
              <IpTypeBadge type={h.ip_type} />
            </div>
          </div>
        </div>
      )}

      {/* Security Protocols */}
      {h.security_protocols?.length > 0 && (
        <div className="casino-card p-6">
          <h3 className="text-casino-gold font-bold text-sm uppercase tracking-widest mb-4">
            Security Protocols
          </h3>
          <div className="flex flex-wrap gap-2">
            {h.security_protocols.map((proto, i) => (
              <span key={i} className="badge badge-completed">{proto}</span>
            ))}
          </div>
        </div>
      )}

      {/* RDP Login Screen Screenshot */}
      {h.screenshot_path && (
        <div className="casino-card p-6">
          <h3 className="text-casino-gold font-bold text-sm uppercase tracking-widest mb-4">
            RDP Login Screen
          </h3>
          <img
            src={`/api/screenshots/${h.screenshot_path.split('/').pop()}`}
            alt={`RDP login screen for ${h.ip}`}
            className="rounded-lg border border-casino-gold/20 max-w-full"
          />
        </div>
      )}

      {/* VNC Desktop Screenshot */}
      {h.vnc_screenshot_path && (
        <div className="casino-card p-6">
          <h3 className="text-purple-400 font-bold text-sm uppercase tracking-widest mb-4">
            VNC Desktop
          </h3>
          <img
            src={`/api/screenshots/${h.vnc_screenshot_path.split('/').pop()}`}
            alt={`VNC desktop for ${h.ip}`}
            className="rounded-lg border border-purple-500/20 max-w-full"
          />
        </div>
      )}

      {/* Web Service Screenshots */}
      {h.web_screenshots?.length > 0 && (
        <div className="casino-card p-6">
          <h3 className="text-blue-400 font-bold text-sm uppercase tracking-widest mb-4">
            Web Services ({h.web_screenshots.length})
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {h.web_screenshots.map((ws, i) => (
              <div key={i} className="border border-blue-500/20 rounded-lg overflow-hidden">
                <div className="bg-blue-500/10 px-4 py-2 flex items-center justify-between">
                  <span className="text-blue-400 font-bold text-sm">:{ws.port}</span>
                  <span className="text-gray-300 text-sm truncate mx-2">{ws.title || 'Untitled'}</span>
                  <a
                    href={ws.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-blue-400 hover:text-blue-300 text-xs font-mono"
                  >
                    {ws.url}
                  </a>
                </div>
                <img
                  src={`/api/screenshots/${ws.screenshot_path.split('/').pop()}`}
                  alt={`Web service on port ${ws.port}`}
                  className="w-full"
                />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Port table */}
      <div className="casino-card p-6">
        <h3 className="text-casino-gold font-bold text-sm uppercase tracking-widest mb-4">
          Open Ports ({h.all_ports?.length ?? 0})
        </h3>
        {h.all_ports?.length === 0 ? (
          <p className="text-gray-500 italic">No port data available.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Port</th>
                <th>Protocol</th>
                <th>Service</th>
                <th>Product</th>
                <th>Version</th>
              </tr>
            </thead>
            <tbody>
              {h.all_ports?.map((p, i) => (
                <tr key={i}>
                  <td className={`font-bold ${(p.port === 3389 || p.port === 3390) ? 'text-casino-neon' : (p.port === 5900 || p.port === 5901) ? 'text-purple-400' : webPorts.has(p.port) ? 'text-blue-400' : 'text-white'}`}>
                    {p.port}
                  </td>
                  <td className="text-gray-400">{p.protocol}</td>
                  <td className="text-gray-300">{p.service}</td>
                  <td className="text-gray-300">{p.product || '—'}</td>
                  <td className="text-gray-400">{p.version || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between border-b border-white/5 pb-2">
      <span className="text-gray-400 text-sm uppercase tracking-wider">{label}</span>
      <span className="font-mono text-sm text-white">{value || '—'}</span>
    </div>
  )
}

function IpTypeBadge({ type }: { type: string }) {
  if (!type) return <span className="font-mono text-sm text-white">—</span>
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
