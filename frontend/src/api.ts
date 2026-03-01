import type {
  Subnet, Scan, Host, HostStats, FeedTarget, VncRandomHost,
  GeoipStatus, GeoipCountry, GeoipState, GeoipCity, GeoipBlocksResponse, BulkSubnetResponse,
} from './types'

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
export const reannounceHost = (id: number) =>
  request<{ message: string }>(`/hosts/${id}/reannounce`, { method: 'POST' })

// GeoIP
export const getGeoipStatus = () => request<GeoipStatus>('/geoip/status')
export const triggerGeoipImport = () =>
  request<{ message: string }>('/geoip/import', { method: 'POST' })
export const getGeoipCountries = () => request<GeoipCountry[]>('/geoip/countries')
export const getGeoipStates = (country: string) =>
  request<GeoipState[]>(`/geoip/states?country=${encodeURIComponent(country)}`)
export const getGeoipCities = (country: string, state: string) =>
  request<GeoipCity[]>(`/geoip/cities?country=${encodeURIComponent(country)}&state=${encodeURIComponent(state)}`)
export const getGeoipBlocks = (country: string, state: string, city: string, page = 1, pageSize = 50) =>
  request<GeoipBlocksResponse>(
    `/geoip/blocks?country=${encodeURIComponent(country)}&state=${encodeURIComponent(state)}&city=${encodeURIComponent(city)}&page=${page}&page_size=${pageSize}`
  )
export const addGeoipSubnets = (cidrs: string[], label = '') =>
  request<BulkSubnetResponse>('/geoip/add-subnets', {
    method: 'POST',
    body: JSON.stringify({ cidrs, label }),
  })
