// Ported from mathaba-experimental. Same layout (evaluation track, developer
// realisation, foot traffic, business presence); data now comes from the
// served profile and tiers from profile.tiers instead of hard-coded values.

import { C, cap, mono } from '../theme'
import type { Asset } from '../types'
import { signalsFromProfile, SIGNAL_PATHS } from '../externalSignals'
import { ServedTierBadge } from './TierBadge'
import { METRICS, authorityGroup, formatValue } from '../config/metricConfig'

function Title({ text }: { text: string }) {
  return (
    <div style={{ ...cap, fontSize: 10.5, color: C.faint, borderBottom: `1px solid ${C.line}`, paddingBottom: 6, marginBottom: 4, marginTop: 20, letterSpacing: '0.08em' }}>
      {text}
    </div>
  )
}

function Row({ asset, path, value, label, warn, text }: {
  asset: Asset
  path: string
  value: unknown
  label?: string
  warn?: boolean
  /** Pre-formatted value text (for composite values). */
  text?: string
}) {
  if (value === null || value === undefined) return null
  const def = METRICS[path]
  const f = text ? { text, unit: undefined } : formatValue(value, def.format, def.unit)
  const isWarn = warn ?? (typeof value === 'number' && !!def.warn?.(value))
  return (
    <div className="metric-row">
      <span className="metric-label">{label ?? def.label}</span>
      <span className="metric-value" style={{ ...mono, color: isWarn ? C.bad : C.text }}>
        {f.text}{f.unit && <span className="metric-unit">{f.unit}</span>}
      </span>
      <ServedTierBadge tier={asset.profile?.tiers?.[path]} />
    </div>
  )
}

// What SDP's relationship to the asset is, in words a judge understands.
const WHY: Record<string, string> = {
  sold: 'Sime Darby sold this asset, so its operating figures are estimates from external proxies, not records.',
  public: 'This asset was handed to the local council, so it is judged on community and environmental value.',
}

// Two-track evaluation: retained assets are judged on operating performance; sold assets on
// developer realisation + community value, using external proxies for what SDP can't observe.
export function ExternalSignalsPanel({ asset }: { asset: Asset }) {
  const profile = asset.profile
  if (!profile?.authority) return null
  const group = authorityGroup(profile)
  const owned = group === 'owned'
  const signals = owned ? {} : signalsFromProfile(profile)
  const { lbs, places, sale } = signals
  const isolated = lbs?.flowIsland != null && lbs.flowIsland < 0.3
  const hasSignals = !!(lbs || places || sale)

  return (
    <>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginTop: 16, fontSize: 12 }}>
        <span style={{ ...cap, fontSize: 10, color: C.faint }}>Evaluation track</span>
        <span style={{ color: owned ? '#3fb27f' : '#f7931d', fontWeight: 600 }}>
          {owned ? 'Operating performance' : 'Developer realisation + community value'}
        </span>
      </div>
      {!owned && (
        <p style={{ margin: '6px 0 0', fontSize: 11.5, color: C.faint, lineHeight: 1.5 }}>
          {WHY[group]}
        </p>
      )}

      {sale && (
        <>
          <Title text="Developer realisation" />
          <Row asset={asset} path={SIGNAL_PATHS.price} value={sale.price} />
          <Row asset={asset} path={SIGNAL_PATHS.date} value={sale.date} />
          <Row asset={asset} path={SIGNAL_PATHS.profit} value={sale.profit} />
          <Row asset={asset} path={SIGNAL_PATHS.saleReturn} value={sale.saleReturn} />
        </>
      )}

      {lbs && (
        <>
          <Title text="Foot traffic (LBS)" />
          <Row asset={asset} path={SIGNAL_PATHS.users} value={lbs.users} />
          <Row asset={asset} path={SIGNAL_PATHS.dwell} value={lbs.dwell} />
          <Row
            asset={asset} path={SIGNAL_PATHS.flowIsland} value={lbs.flowIsland}
            label={isolated ? 'Flow-island ratio · network-isolated' : undefined}
          />
          <Row asset={asset} path={SIGNAL_PATHS.proxOcc} value={lbs.proxOcc} />
          <Row asset={asset} path={SIGNAL_PATHS.traffic} value={lbs.traffic} />
        </>
      )}

      {places && (
        <>
          <Title text="Business presence (Google Places)" />
          <Row
            asset={asset} path={SIGNAL_PATHS.presence} value={places.presence}
            text={places.operational != null && places.units != null && places.presence != null
              ? `${places.operational} of ${places.units} (${formatValue(places.presence, 'ratio').text})`
              : undefined}
          />
          <Row asset={asset} path={SIGNAL_PATHS.vitality} value={places.vitality} />
          <Row asset={asset} path={SIGNAL_PATHS.vacancyMonths} value={places.vacancyMonths} />
          <Row asset={asset} path={SIGNAL_PATHS.turnover} value={places.turnover} />
        </>
      )}

      {group === 'sold' && !hasSignals && (
        <p style={{ margin: '10px 0 0', fontSize: 11.5, color: C.faint }}>No external signal data for this asset.</p>
      )}
    </>
  )
}
