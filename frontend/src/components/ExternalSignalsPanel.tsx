// Ported from mathaba-experimental. Same sections (developer realisation,
// foot traffic, business presence); data comes from the served profile and
// tiers from profile.tiers. The evaluation-track line now lives in the
// AssetPanel header. Rows whose value is already shown under a diagnosis flag
// are hidden (`hidden`), so each value appears once in the panel.

import { C, cap, mono } from '../theme'
import type { Asset } from '../types'
import { signalsFromProfile, SIGNAL_PATHS } from '../externalSignals'
import { ServedTierBadge } from './TierBadge'
import { METRICS, authorityGroup, formatValue } from '../config/metricConfig'

function Title({ text }: { text: string }) {
  return (
    <div style={{ ...cap, fontSize: 10.5, color: C.faint, borderBottom: `1px solid ${C.line}`, paddingBottom: 6, marginBottom: 2, marginTop: 18, letterSpacing: '0.08em' }}>
      {text}
    </div>
  )
}

function Row({ asset, path, value, label, text, hidden }: {
  asset: Asset
  path: string
  value: unknown
  label?: string
  /** Pre-formatted value text (for composite values). */
  text?: string
  hidden: Set<string>
}) {
  if (value === null || value === undefined || hidden.has(path)) return null
  const def = METRICS[path]
  const f = text ? { text, unit: undefined } : formatValue(value, def.format, def.unit)
  const warn = typeof value === 'number' && !!def.warn?.(value)
  return (
    <div className="metric-row">
      <span className="metric-label">{label ?? def.label}</span>
      <span className="metric-value" style={{ ...mono, color: warn ? C.bad : C.text }}>
        {f.text}{f.unit && <span className="metric-unit">{f.unit}</span>}
      </span>
      <ServedTierBadge tier={asset.profile?.tiers?.[path]} />
    </div>
  )
}

/** True when the asset has anything for this panel to show. */
export function hasExternalSignals(asset: Asset): boolean {
  if (authorityGroup(asset.profile) === 'owned') return false
  const s = signalsFromProfile(asset.profile)
  return !!(s.lbs || s.places || s.sale)
}

export function ExternalSignalsPanel({ asset, hidden = new Set<string>() }: { asset: Asset; hidden?: Set<string> }) {
  if (!hasExternalSignals(asset)) return null
  const { lbs, places, sale } = signalsFromProfile(asset.profile)
  const isolated = lbs?.flowIsland != null && lbs.flowIsland < 0.3
  const visible = (paths: string[], values: unknown[]) =>
    paths.some((p, i) => values[i] != null && !hidden.has(p))

  return (
    <>
      {sale && visible(
        [SIGNAL_PATHS.price, SIGNAL_PATHS.date, SIGNAL_PATHS.profit, SIGNAL_PATHS.saleReturn],
        [sale.price, sale.date, sale.profit, sale.saleReturn],
      ) && (
        <>
          <Title text="Developer realisation" />
          <Row asset={asset} hidden={hidden} path={SIGNAL_PATHS.price} value={sale.price} />
          <Row asset={asset} hidden={hidden} path={SIGNAL_PATHS.date} value={sale.date} />
          <Row asset={asset} hidden={hidden} path={SIGNAL_PATHS.profit} value={sale.profit} />
          <Row asset={asset} hidden={hidden} path={SIGNAL_PATHS.saleReturn} value={sale.saleReturn} />
        </>
      )}

      {lbs && visible(
        [SIGNAL_PATHS.users, SIGNAL_PATHS.dwell, SIGNAL_PATHS.flowIsland, SIGNAL_PATHS.proxOcc, SIGNAL_PATHS.traffic],
        [lbs.users, lbs.dwell, lbs.flowIsland, lbs.proxOcc, lbs.traffic],
      ) && (
        <>
          <Title text="Foot traffic (LBS)" />
          <Row asset={asset} hidden={hidden} path={SIGNAL_PATHS.users} value={lbs.users} />
          <Row asset={asset} hidden={hidden} path={SIGNAL_PATHS.dwell} value={lbs.dwell} />
          <Row
            asset={asset} hidden={hidden} path={SIGNAL_PATHS.flowIsland} value={lbs.flowIsland}
            label={isolated ? 'Flow-island ratio · network-isolated' : undefined}
          />
          <Row asset={asset} hidden={hidden} path={SIGNAL_PATHS.proxOcc} value={lbs.proxOcc} />
          <Row asset={asset} hidden={hidden} path={SIGNAL_PATHS.traffic} value={lbs.traffic} />
        </>
      )}

      {places && visible(
        [SIGNAL_PATHS.presence, SIGNAL_PATHS.vitality, SIGNAL_PATHS.vacancyMonths, SIGNAL_PATHS.turnover],
        [places.presence, places.vitality, places.vacancyMonths, places.turnover],
      ) && (
        <>
          <Title text="Business presence (Google Places)" />
          <Row
            asset={asset} hidden={hidden} path={SIGNAL_PATHS.presence} value={places.presence}
            text={places.operational != null && places.units != null && places.presence != null
              ? `${places.operational} of ${places.units} (${formatValue(places.presence, 'ratio').text})`
              : undefined}
          />
          <Row asset={asset} hidden={hidden} path={SIGNAL_PATHS.vitality} value={places.vitality} />
          <Row asset={asset} hidden={hidden} path={SIGNAL_PATHS.vacancyMonths} value={places.vacancyMonths} />
          <Row asset={asset} hidden={hidden} path={SIGNAL_PATHS.turnover} value={places.turnover} />
        </>
      )}
    </>
  )
}
