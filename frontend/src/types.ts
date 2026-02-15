export interface Subnet {
  id: number
  cidr: string
  label: string
  is_active: number
  created_at: string
  updated_at: string
}

export interface Scan {
  id: number
  subnet_id: number
  subnet_cidr: string | null
  subnet_label: string | null
  status: 'pending' | 'running' | 'completed' | 'failed'
  hosts_found: number
  rdp_found: number
  vnc_found: number
  started_at: string | null
  finished_at: string | null
  error: string | null
  created_at: string
}

export interface PortInfo {
  port: number
  protocol: string
  service: string
  version: string
  product: string
}

export interface Host {
  id: number
  scan_id: number
  subnet_id: number
  ip: string
  hostname: string
  netbios_name: string
  domain: string
  os_guess: string
  rdp_open: number
  all_ports: PortInfo[]
  mac_address: string
  first_seen_at: string
  last_seen_at: string
  announced: number
  nla_required: number | null
  security_protocols: string[]
  screenshot_path: string
  asn: string
  isp: string
  org: string
  country: string
  country_code: string
  city: string
  latitude: number | null
  longitude: number | null
  ip_type: string
  reverse_dns: string
  vnc_open: number
  vnc_auth_required: number | null
  vnc_desktop_name: string
  vnc_screenshot_path: string
}

export interface HostStats {
  total_hosts: number
  rdp_open: number
  vnc_open: number
  subnets_scanned: number
  total_scans: number
  announced: number
}

export interface FeedTarget {
  ip: string
  label: string
}

export interface VncRandomHost {
  ip: string
  subnet_cidr: string
  country: string
  city: string
  asn: string
  desktop_name: string
}
