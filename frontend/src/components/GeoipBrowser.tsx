import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getGeoipStatus,
  triggerGeoipImport,
  getGeoipCountries,
  getGeoipStates,
  getGeoipCities,
  getGeoipBlocks,
  addGeoipSubnets,
} from '../api'
import type { GeoipBlock } from '../types'

export default function GeoipBrowser() {
  const qc = useQueryClient()
  const [country, setCountry] = useState('')
  const [state, setState] = useState('')
  const [city, setCity] = useState('')
  const [page, setPage] = useState(1)
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [label, setLabel] = useState('')
  const [result, setResult] = useState<{ created: number; skipped: number } | null>(null)

  const status = useQuery({
    queryKey: ['geoip-status'],
    queryFn: getGeoipStatus,
    refetchInterval: (query) => query.state.data?.import_running ? 2000 : false,
  })

  const importDb = useMutation({
    mutationFn: triggerGeoipImport,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['geoip-status'] }),
  })

  const countries = useQuery({
    queryKey: ['geoip-countries'],
    queryFn: getGeoipCountries,
    enabled: !!status.data?.imported && !status.data?.import_running,
  })

  const states = useQuery({
    queryKey: ['geoip-states', country],
    queryFn: () => getGeoipStates(country),
    enabled: !!country,
  })

  const cities = useQuery({
    queryKey: ['geoip-cities', country, state],
    queryFn: () => getGeoipCities(country, state),
    enabled: !!country && !!state,
  })

  const blocks = useQuery({
    queryKey: ['geoip-blocks', country, state, city, page],
    queryFn: () => getGeoipBlocks(country, state, city, page),
    enabled: !!country && !!state && !!city,
  })

  const bulkAdd = useMutation({
    mutationFn: (cidrs: string[]) => addGeoipSubnets(cidrs, label),
    onSuccess: (data) => {
      setResult(data)
      setSelected(new Set())
      qc.invalidateQueries({ queryKey: ['subnets'] })
      qc.invalidateQueries({ queryKey: ['scans'] })
      qc.invalidateQueries({ queryKey: ['activeScans'] })
    },
  })

  const handleCountryChange = (val: string) => {
    setCountry(val)
    setState('')
    setCity('')
    setPage(1)
    setSelected(new Set())
    setResult(null)
  }

  const handleStateChange = (val: string) => {
    setState(val)
    setCity('')
    setPage(1)
    setSelected(new Set())
    setResult(null)
  }

  const handleCityChange = (val: string) => {
    setCity(val)
    setPage(1)
    setSelected(new Set())
    setResult(null)
    if (val) {
      setLabel([val, state, country].filter(Boolean).join(', '))
    }
  }

  const toggleBlock = (idx: number) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(idx)) next.delete(idx)
      else next.add(idx)
      return next
    })
  }

  const toggleAll = () => {
    if (!blocks.data) return
    if (selected.size === blocks.data.blocks.length) {
      setSelected(new Set())
    } else {
      setSelected(new Set(blocks.data.blocks.map((_, i) => i)))
    }
  }

  const getSelectedCidrs = (): string[] => {
    if (!blocks.data) return []
    const cidrs: string[] = []
    for (const idx of selected) {
      const block = blocks.data.blocks[idx]
      if (block) cidrs.push(...block.cidrs)
    }
    return cidrs
  }

  const selectedCidrs = getSelectedCidrs()

  return (
    <div className="space-y-8">
      <div>
        <h2 className="font-display text-3xl font-black text-casino-gold">
          GeoIP Browser
        </h2>
        <p className="text-gray-400 mt-1">
          Discover scannable subnets by geographic location.
        </p>
      </div>

      {/* Import Status Card */}
      <div className="casino-card p-6">
        <h3 className="text-casino-gold font-bold text-sm uppercase tracking-widest mb-4">
          Database Status
        </h3>
        {status.isLoading ? (
          <p className="text-gray-500 italic">Loading...</p>
        ) : status.data ? (
          <div className="space-y-4">
            <div className="flex items-center gap-6 text-sm">
              <div>
                <span className="text-gray-400">Status: </span>
                {status.data.imported ? (
                  <span className="badge badge-completed">Imported</span>
                ) : (
                  <span className="badge badge-pending">Not Imported</span>
                )}
              </div>
              {status.data.total_blocks > 0 && (
                <div>
                  <span className="text-gray-400">Blocks: </span>
                  <span className="text-white font-mono">
                    {status.data.total_blocks.toLocaleString()}
                  </span>
                </div>
              )}
              {status.data.csv_date && (
                <div>
                  <span className="text-gray-400">CSV Date: </span>
                  <span className="text-white">{status.data.csv_date}</span>
                </div>
              )}
              {status.data.last_updated && (
                <div>
                  <span className="text-gray-400">Last Updated: </span>
                  <span className="text-white">
                    {new Date(status.data.last_updated).toLocaleDateString()}
                  </span>
                </div>
              )}
            </div>

            {status.data.import_running && (
              <div className="space-y-2">
                <div className="flex items-center gap-2 text-sm text-casino-neon">
                  <span className="animate-spin inline-block w-4 h-4 border-2 border-casino-neon border-t-transparent rounded-full" />
                  Importing...
                  {status.data.import_progress !== null && status.data.import_progress > 0 && (
                    <span className="text-gray-400">
                      ({status.data.import_progress.toLocaleString()} blocks)
                    </span>
                  )}
                </div>
                <div className="w-full bg-black/40 rounded-full h-2 overflow-hidden">
                  <div
                    className="h-full bg-casino-neon rounded-full transition-all animate-pulse"
                    style={{ width: status.data.import_progress ? `${Math.min((status.data.import_progress / 4000000) * 100, 95)}%` : '10%' }}
                  />
                </div>
              </div>
            )}

            <button
              className="btn-neon"
              onClick={() => importDb.mutate()}
              disabled={importDb.isPending || status.data.import_running}
            >
              {status.data.imported ? 'Re-Import Database' : 'Import Database'}
            </button>
            {importDb.isError && (
              <p className="text-casino-red-bright text-sm">
                {(importDb.error as Error).message}
              </p>
            )}
          </div>
        ) : null}
      </div>

      {/* Drill-down Card */}
      {status.data?.imported && !status.data.import_running && (
        <div className="casino-card p-6">
          <h3 className="text-casino-gold font-bold text-sm uppercase tracking-widest mb-4">
            Browse by Location
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* Country */}
            <div>
              <label className="block text-xs text-gray-400 uppercase tracking-wider mb-1">
                Country
              </label>
              <select
                value={country}
                onChange={(e) => handleCountryChange(e.target.value)}
                className="w-full bg-black/40 border border-white/10 rounded-lg px-3 py-2 text-white text-sm"
              >
                <option value="">Select country...</option>
                {countries.data?.map((c) => (
                  <option key={c.country} value={c.country}>
                    {c.country} ({c.block_count.toLocaleString()})
                  </option>
                ))}
              </select>
            </div>

            {/* State */}
            <div>
              <label className="block text-xs text-gray-400 uppercase tracking-wider mb-1">
                State / Region
              </label>
              <select
                value={state}
                onChange={(e) => handleStateChange(e.target.value)}
                disabled={!country}
                className="w-full bg-black/40 border border-white/10 rounded-lg px-3 py-2 text-white text-sm disabled:opacity-40"
              >
                <option value="">Select state...</option>
                {states.data?.map((s) => (
                  <option key={s.state} value={s.state}>
                    {s.state} ({s.block_count.toLocaleString()})
                  </option>
                ))}
              </select>
            </div>

            {/* City */}
            <div>
              <label className="block text-xs text-gray-400 uppercase tracking-wider mb-1">
                City
              </label>
              <select
                value={city}
                onChange={(e) => handleCityChange(e.target.value)}
                disabled={!state}
                className="w-full bg-black/40 border border-white/10 rounded-lg px-3 py-2 text-white text-sm disabled:opacity-40"
              >
                <option value="">Select city...</option>
                {cities.data?.map((c) => (
                  <option key={c.city} value={c.city}>
                    {c.city} ({c.block_count.toLocaleString()})
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>
      )}

      {/* Results Table */}
      {blocks.data && blocks.data.blocks.length > 0 && (
        <div className="casino-card p-6">
          <h3 className="text-casino-gold font-bold text-sm uppercase tracking-widest mb-4">
            IP Blocks — {city}, {state}, {country}
            <span className="text-gray-400 font-normal ml-2">
              ({blocks.data.total.toLocaleString()} blocks)
            </span>
          </h3>
          <table>
            <thead>
              <tr>
                <th className="w-10">
                  <input
                    type="checkbox"
                    checked={selected.size === blocks.data.blocks.length && blocks.data.blocks.length > 0}
                    onChange={toggleAll}
                    className="accent-casino-neon"
                  />
                </th>
                <th>IP Range</th>
                <th>Total IPs</th>
                <th>/24 Subnets</th>
                <th>ASN / ISP</th>
                <th>Type</th>
              </tr>
            </thead>
            <tbody>
              {blocks.data.blocks.map((block: GeoipBlock, idx: number) => (
                <tr key={idx} className={selected.has(idx) ? 'bg-casino-gold/5' : ''}>
                  <td>
                    <input
                      type="checkbox"
                      checked={selected.has(idx)}
                      onChange={() => toggleBlock(idx)}
                      className="accent-casino-neon"
                    />
                  </td>
                  <td className="font-mono text-white text-sm">
                    {block.ip_start} — {block.ip_end}
                  </td>
                  <td className="text-gray-300">{block.total_ips.toLocaleString()}</td>
                  <td>
                    <span className="badge badge-completed">{block.cidr_count}</span>
                  </td>
                  <td className="text-sm">
                    {block.asn && <span className="text-white font-mono">{block.asn}</span>}
                    {block.isp && <span className="text-gray-400 ml-1">{block.isp}</span>}
                  </td>
                  <td>
                    {block.ip_type && (
                      <span className={`badge ${
                        block.ip_type === 'Residential' ? 'badge-completed' :
                        block.ip_type === 'Datacenter' ? 'badge-running' :
                        'badge-pending'
                      }`}>
                        {block.ip_type}
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {/* Pagination */}
          {blocks.data.total_pages > 1 && (
            <div className="flex items-center justify-between mt-4 text-sm">
              <span className="text-gray-400">
                Page {blocks.data.page} of {blocks.data.total_pages}
              </span>
              <div className="flex gap-2">
                <button
                  className="btn-neon btn-sm"
                  disabled={page <= 1}
                  onClick={() => { setPage((p) => p - 1); setSelected(new Set()) }}
                >
                  Prev
                </button>
                <button
                  className="btn-neon btn-sm"
                  disabled={page >= blocks.data.total_pages}
                  onClick={() => { setPage((p) => p + 1); setSelected(new Set()) }}
                >
                  Next
                </button>
              </div>
            </div>
          )}

          {/* Action Bar */}
          <div className="mt-6 pt-4 border-t border-white/10 flex items-end gap-3">
            <div className="flex-1">
              <label className="block text-xs text-gray-400 uppercase tracking-wider mb-1">
                Subnet Label
              </label>
              <input
                type="text"
                value={label}
                onChange={(e) => setLabel(e.target.value)}
                placeholder={`${city}, ${country}`}
                className="w-full"
              />
            </div>
            <button
              className="btn-neon"
              disabled={selectedCidrs.length === 0 || bulkAdd.isPending}
              onClick={() => bulkAdd.mutate(selectedCidrs)}
            >
              {bulkAdd.isPending
                ? 'Adding...'
                : `Add & Scan ${selectedCidrs.length} Subnet${selectedCidrs.length !== 1 ? 's' : ''}`}
            </button>
          </div>
          {result && (
            <p className="text-sm mt-2 text-casino-neon">
              {result.created} added & queued for scanning, {result.skipped} duplicates skipped
            </p>
          )}
          {bulkAdd.isError && (
            <p className="text-casino-red-bright text-sm mt-2">
              {(bulkAdd.error as Error).message}
            </p>
          )}
        </div>
      )}

      {/* Empty state when city selected but no blocks with /24s */}
      {blocks.data && blocks.data.blocks.length === 0 && city && (
        <div className="casino-card p-6">
          <p className="text-gray-500 italic">No IP blocks found for this location.</p>
        </div>
      )}
    </div>
  )
}
