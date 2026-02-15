import type { Subnet, Scan, Host, HostStats, FeedTarget, VncRandomHost } from './types'

const BASE = '/api'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(`${res.status}: ${body}`)
  }
  if (res.status === 204) return undefined as T
  return res.json()
}

// Subnets
export const listSubnets = () => request<Subnet[]>('/subnets')
export const createSubnet = (cidr: string, label = '') =>
  request<Subnet>('/subnets', { method: 'POST', body: JSON.stringify({ cidr, label }) })
export const updateSubnet = (id: number, data: Partial<Subnet>) =>
  request<Subnet>(`/subnets/${id}`, { method: 'PATCH', body: JSON.stringify(data) })
export const deleteSubnet = (id: number) =>
  request<void>(`/subnets/${id}`, { method: 'DELETE' })

// Scans
export const listScans = (subnetId?: number) =>
  request<Scan[]>(`/scans${subnetId ? `?subnet_id=${subnetId}` : ''}`)
export const triggerScan = (subnetId?: number) =>
  request<Scan[]>('/scans', {
    method: 'POST',
    body: JSON.stringify(subnetId ? { subnet_id: subnetId } : {}),
  })
export const getActiveScans = () => request<Scan[]>('/scans/active')
export const getFeedTargets = () => request<FeedTarget[]>('/scans/feed-targets')
export const getVncRandom = () => request<VncRandomHost>('/scans/vnc-random')

// Hosts
export const listHosts = (opts?: { subnetId?: number; rdpOnly?: boolean; vncOnly?: boolean }) => {
  const params = new URLSearchParams()
  if (opts?.subnetId) params.set('subnet_id', String(opts.subnetId))
  if (opts?.rdpOnly) params.set('rdp_only', 'true')
  if (opts?.vncOnly) params.set('vnc_only', 'true')
  const qs = params.toString()
  return request<Host[]>(`/hosts${qs ? `?${qs}` : ''}`)
}
export const getHost = (id: number) => request<Host>(`/hosts/${id}`)
export const getHostStats = () => request<HostStats>('/hosts/stats')
