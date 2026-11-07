import { useEffect, useState } from 'react'
import { C, cap, mono } from '../theme'
import type { Asset } from '../types'
import { loadExternalSignals, type ExternalSignals } from '../externalSignals'
import { TierBadge, type Tier } from './TierBadge'

const pct = (v: number | null) => (v == null ? '—' : `${(v * 100).toFixed(1)}%`)
const n1 = (v: number | null, digits = 1) => (v == null ? '—' : v.toLocaleString(undefined, { maximumFractionDigits: digits }))

function Title({ text }: { text: string }) {
  return (
    <div style={{ ...cap, fontSize: 11, color: C.faint, borderBottom: `1px solid ${C.line}`, paddingBottom: 6, marginBottom: 10, marginTop: 22, letterSpacing: '0.05em' }}>
      {text}
    </div>
  )
}

function Row({ label, value, tier, mock, warn }: { label: string; value: string; tier: Tier; mock?: boolean; warn?: boolean }) {
  return (
    <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, padding: '6px 0', fontSize: 12.5, borderBottom: `1px dashed ${C.line}` }}>
      <span style={{ color: C.muted }}>{label}</span>
      <span style={{ ...mono, marginLeft: 'auto', fontWeight: 500, color: warn ? '#d71920' : C.text }}>{value}</span>
      <TierBadge tier={tier} mock={mock} />
    </div>
  )
}

// Two-track evaluation: retained assets are judged on operating performance; sold assets on
// developer realisation + community value, using external proxies for what SDP can't observe.
export function ExternalSignalsPanel({ asset }: { asset: Asset }) {
  const [signals, setSignals] = useState<ExternalSignals | null | undefined>(undefined)

  useEffect(() => {
    let live = true
    loadExternalSignals().then((m) => { if (live) setSignals(m.get(asset.id) ?? null) })
    return () => { live = false }
  }, [asset.id])

  const level = asset.profile?.authority?.level
  if (!level) return null
  const sold = level !== 'full_control'
  // What SDP's relationship to the asset is, in words a judge understands.
  const why: Record<string, string> = {
    sold: 'Sime Darby sold this asset, so its operating figures are estimates from external proxies, not records.',
    shared: 'This asset is jointly managed, so some operating figures are estimates from external proxies.',
    advisory: 'Sime Darby can only advise on this asset, so its operating figures are estimates from external proxies, not records.',
    public_transferred: 'This asset was handed to the local council, so it is judged on community and environmental value.',
  }

  const lbs = sold ? signals?.lbs : undefined
  const sale = sold ? signals?.sale : undefined
  const profit = sale?.price != null && sale.capex != null ? sale.price - sale.capex : null
  const saleReturn = profit != null && sale?.capex ? profit / sale.capex : null
  const rm = (v: number | null) => (v == null ? '—' : `RM ${Math.round(v).toLocaleString()}`)
  const places = sold ? signals?.places : undefined
  const isolated = lbs?.flowIsland != null && lbs.flowIsland < 0.3

  return (
    <>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginTop: 16, fontSize: 12 }}>
        <span style={{ ...cap, fontSize: 10, color: C.faint }}>Evaluation track</span>
        <span style={{ color: sold ? '#f7931d' : '#3fb27f', fontWeight: 600 }}>
          {sold ? 'Developer realisation + community value' : 'Operating performance'}
        </span>
      </div>
      {sold && (
        <p style={{ margin: '6px 0 0', fontSize: 11.5, color: C.faint, lineHeight: 1.5 }}>
          {why[level] ?? 'Operating figures for this asset are estimates from external proxies, not records.'}
        </p>
      )}

      {sale && (
        <>
          <Title text="Developer realisation" />
          <Row label="Sale price" value={rm(sale.price)} tier="1" />
          {sale.date && <Row label="Sold on" value={sale.date} tier="1" />}
          <Row label="Profit vs build cost" value={rm(profit)} tier="2" warn={profit != null && profit < 0} />
          <Row label="Return on build cost" value={pct(saleReturn)} tier="2" warn={saleReturn != null && saleReturn < 0} />
        </>
      )}

      {lbs && (
        <>
          <Title text="Foot traffic (LBS)" />
          <Row label="Daily unique visitors" value={n1(lbs.users)} tier="3a" mock={lbs.isMock} />
          <Row label="Average stay" value={lbs.dwell == null ? '—' : `${n1(lbs.dwell)} min`} tier="3a" mock={lbs.isMock} />
          <Row
            label={isolated ? 'Flow-island ratio · network-isolated' : 'Flow-island ratio'}
            value={n1(lbs.flowIsland, 2)} tier="3a" mock={lbs.isMock} warn={isolated}
          />
          <Row label="Occupancy estimated from footfall" value={pct(lbs.proxOcc)} tier="3a" mock={lbs.isMock} />
          <Row label="Passing traffic" value={lbs.traffic == null ? '—' : `${n1(lbs.traffic, 0)} vehicles/day`} tier="3a" mock={lbs.isMock} />
        </>
      )}

      {places && (
        <>
          <Title text="Business presence (Google Places)" />
          <Row
            label="Units with an operating business"
            value={places.operational != null && places.units != null
              ? `${places.operational} of ${places.units} (${pct(places.presence)})`
              : pct(places.presence)}
            tier="3a" mock={places.isMock}
          />
          <Row label="Business vitality" value={n1(places.vitality, 2)} tier="3a" mock={places.isMock} />
          <Row label="Estimated vacancy" value={places.vacancyMonths == null ? '—' : `${n1(places.vacancyMonths, 0)} months`} tier="3a" mock={places.isMock} />
          <Row label="Business turnover" value={n1(places.turnover, 0)} tier="3a" mock={places.isMock} />
        </>
      )}

      {sold && signals === null && (
        <p style={{ margin: '10px 0 0', fontSize: 11.5, color: C.faint }}>No external signal data for this asset.</p>
      )}
    </>
  )
}