import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { listSubnets, createSubnet, updateSubnet, deleteSubnet, triggerScan, getFeedTargets, getVncRandom } from '../api'
import type { VncRandomHost } from '../types'

export default function SubnetManager() {
  const qc = useQueryClient()
  const [cidr, setCidr] = useState('')
  const [label, setLabel] = useState('')

  const subnets = useQuery({ queryKey: ['subnets'], queryFn: listSubnets })

  const addSubnet = useMutation({
    mutationFn: () => createSubnet(cidr, label),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['subnets'] })
      setCidr('')
      setLabel('')
    },
  })

  const toggle = useMutation({
    mutationFn: ({ id, is_active }: { id: number; is_active: number }) =>
      updateSubnet(id, { is_active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['subnets'] }),
  })

  const remove = useMutation({
    mutationFn: deleteSubnet,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['subnets'] }),
  })

  const scan = useMutation({
    mutationFn: triggerScan,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['scans'] })
      qc.invalidateQueries({ queryKey: ['activeScans'] })
    },
  })

  const feedTargets = useQuery({
    queryKey: ['feedTargets'],
    queryFn: getFeedTargets,
  })

  const [scanningIp, setScanningIp] = useState<string | null>(null)

  const scanSingleHost = useMutation({
    mutationFn: async (ip: string) => {
      setScanningIp(ip)
      // Compute /24 subnet from the IP
      const octets = ip.split('.')
      const cidr = `${octets[0]}.${octets[1]}.${octets[2]}.0/24`
      const existing = subnets.data?.find((s) => s.cidr === cidr)
      let subnetId: number
      if (existing) {
        subnetId = existing.id
      } else {
        const created = await createSubnet(cidr, `Feed: ${ip}`)
        subnetId = created.id
      }
      return triggerScan(subnetId)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['subnets'] })
      qc.invalidateQueries({ queryKey: ['scans'] })
      qc.invalidateQueries({ queryKey: ['activeScans'] })
      setScanningIp(null)
    },
    onError: () => setScanningIp(null),
  })

  const [vncHost, setVncHost] = useState<VncRandomHost | null>(null)

  const rollVnc = useMutation({
    mutationFn: getVncRandom,
    onSuccess: (data) => setVncHost(data),
  })

  const scanVncSubnet = useMutation({
    mutationFn: async (host: VncRandomHost) => {
      const existing = subnets.data?.find((s) => s.cidr === host.subnet_cidr)
      let subnetId: number
      if (existing) {
        subnetId = existing.id
      } else {
        const label = [host.city, host.country, host.asn].filter(Boolean).join(' / ')
        const created = await createSubnet(host.subnet_cidr, label)
        subnetId = created.id
      }
      return triggerScan(subnetId)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['subnets'] })
      qc.invalidateQueries({ queryKey: ['scans'] })
      qc.invalidateQueries({ queryKey: ['activeScans'] })
    },
  })

  return (
    <div className="space-y-8">
      <div>
        <h2 className="font-display text-3xl font-black text-casino-gold">
          The Card Table
        </h2>
        <p className="text-gray-400 mt-1">Manage your target subnets.</p>
      </div>

      {/* Add subnet form */}
      <div className="casino-card p-6">
        <h3 className="text-casino-gold font-bold text-sm uppercase tracking-widest mb-4">
          Deal a New Subnet
        </h3>
        <form
          onSubmit={(e) => {
            e.preventDefault()
            if (cidr.trim()) addSubnet.mutate()
          }}
          className="flex gap-3 items-end"
        >
          <div className="flex-1">
            <label className="block text-xs text-gray-400 uppercase tracking-wider mb-1">
              CIDR
            </label>
            <input
              type="text"
              value={cidr}
              onChange={(e) => setCidr(e.target.value)}
              placeholder="192.168.1.0/24"
              className="w-full"
            />
          </div>
          <div className="flex-1">
            <label className="block text-xs text-gray-400 uppercase tracking-wider mb-1">
              Label
            </label>
            <input
              type="text"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="Office LAN"
              className="w-full"
            />
          </div>
          <button type="submit" className="btn-neon" disabled={addSubnet.isPending || !cidr.trim()}>
            Add
          </button>
        </form>
        {addSubnet.isError && (
          <p className="text-casino-red-bright text-sm mt-2">
            {(addSubnet.error as Error).message}
          </p>
        )}
      </div>

      {/* Subnet list */}
      <div className="casino-card p-6">
        <h3 className="text-casino-gold font-bold text-sm uppercase tracking-widest mb-4">
          Your Hand
        </h3>
        {subnets.data?.length === 0 ? (
          <p className="text-gray-500 italic">No subnets yet. Deal one above.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>CIDR</th>
                <th>Label</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {subnets.data?.map((subnet) => (
                <tr key={subnet.id}>
                  <td className="text-white font-semibold">{subnet.cidr}</td>
                  <td className="text-gray-300">{subnet.label || '—'}</td>
                  <td>
                    <button
                      onClick={() =>
                        toggle.mutate({
                          id: subnet.id,
                          is_active: subnet.is_active ? 0 : 1,
                        })
                      }
                      className={`badge cursor-pointer ${
                        subnet.is_active ? 'badge-completed' : 'badge-pending'
                      }`}
                    >
                      {subnet.is_active ? 'Active' : 'Inactive'}
                    </button>
                  </td>
                  <td>
                    <div className="flex gap-2">
                      <button
                        className="btn-neon btn-sm"
                        onClick={() => scan.mutate(subnet.id)}
                        disabled={scan.isPending}
                      >
                        Scan
                      </button>
                      <button
                        className="btn-danger btn-sm"
                        onClick={() => remove.mutate(subnet.id)}
                      >
                        Fold
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* VNC Resolver — random /24 */}
      <div className="casino-card p-6">
        <h3 className="text-casino-gold font-bold text-sm uppercase tracking-widest mb-4">
          Lucky Draw
        </h3>
        <p className="text-gray-400 text-xs mb-4">
          Pull a random host from VNC Resolver and scan its /24 subnet.
        </p>
        <div className="flex items-center gap-4">
          <button
            className="btn-neon"
            onClick={() => rollVnc.mutate()}
            disabled={rollVnc.isPending}
          >
            {rollVnc.isPending ? 'Rolling...' : 'Roll the Dice'}
          </button>
          {vncHost && (
            <div className="flex items-center gap-4 bg-black/30 border border-white/10 rounded-lg px-4 py-3 flex-1">
              <div className="flex-1 space-y-1">
                <div className="font-mono text-white text-sm">
                  {vncHost.subnet_cidr}
                  <span className="text-gray-500 ml-2">(from {vncHost.ip})</span>
                </div>
                <div className="text-xs text-gray-400">
                  {[vncHost.city, vncHost.country].filter(Boolean).join(', ')}
                  {vncHost.asn && <span className="ml-2 text-gray-500">{vncHost.asn}</span>}
                  {vncHost.desktop_name && <span className="ml-2 text-casino-neon">{vncHost.desktop_name}</span>}
                </div>
              </div>
              <button
                className="btn-neon btn-sm"
                onClick={() => scanVncSubnet.mutate(vncHost)}
                disabled={scanVncSubnet.isPending}
              >
                {scanVncSubnet.isPending ? 'Scanning...' : 'Scan /24'}
              </button>
            </div>
          )}
        </div>
        {(rollVnc.isError || scanVncSubnet.isError) && (
          <p className="text-casino-red-bright text-sm mt-2">
            {((rollVnc.error || scanVncSubnet.error) as Error).message}
          </p>
        )}
      </div>

      {/* Feed targets — single host scan */}
      <div className="casino-card p-6">
        <h3 className="text-casino-gold font-bold text-sm uppercase tracking-widest mb-4">
          Hot Tips from the Wire
        </h3>
        <p className="text-gray-400 text-xs mb-4">
          Networks sourced from the external feed. Click to scan the /24 subnet.
        </p>
        {feedTargets.isLoading ? (
          <p className="text-gray-500 italic">Loading feed...</p>
        ) : feedTargets.isError ? (
          <p className="text-casino-red-bright text-sm">Failed to load feed.</p>
        ) : feedTargets.data?.length === 0 ? (
          <p className="text-gray-500 italic">No targets available.</p>
        ) : (
          <div className="flex flex-wrap gap-3">
            {feedTargets.data?.map((target) => {
              const octets = target.ip.split('.')
              const subnet = `${octets[0]}.${octets[1]}.${octets[2]}.0/24`
              return (
                <div
                  key={target.ip}
                  className="flex items-center gap-3 bg-black/30 border border-white/10 rounded-lg px-4 py-3"
                >
                  <span className="font-mono text-white text-sm">{subnet}</span>
                  <button
                    className="btn-neon btn-sm"
                    disabled={scanSingleHost.isPending}
                    onClick={() => scanSingleHost.mutate(target.ip)}
                  >
                    {scanningIp === target.ip ? 'Scanning...' : 'Scan'}
                  </button>
                </div>
              )
            })}
          </div>
        )}
        {scanSingleHost.isError && (
          <p className="text-casino-red-bright text-sm mt-2">
            {(scanSingleHost.error as Error).message}
          </p>
        )}
      </div>
    </div>
  )
}
