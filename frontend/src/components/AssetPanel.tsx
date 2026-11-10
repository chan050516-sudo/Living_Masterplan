import { useState, useRef, useEffect } from 'react'
import { C, cap, mono, btn } from '../theme'
import { TierBadge, ServedTierBadge } from './TierBadge'
import { ExternalSignalsPanel, hasExternalSignals } from './ExternalSignalsPanel'
import {
  PILLARS, PANEL_TABS, AUTHORITY_GROUP_LABEL, EVALUATION_TRACK, SUBUNIT_COLUMNS,
  authorityGroup, coreMetricKeys, resolveMetric, placeMetrics, openPillars,
  formatMetric, formatValue, isWarn, humanize,
  assetTypeLabel, subtypeLabel, statusLabel, modeLabel, diagnosisSummary,
  type ResolvedMetric, type Placement, type PanelTab,
} from '../config/metricConfig'
import type { Asset, AnalyzeResult, MainMetric, AssetStatus, InterventionMode, Subunit } from '../types'
import type { AnalyzeHistoryItem } from '../App'

const STATUS_COLOR: Record<AssetStatus, string> = {
  healthy: '#3fb27f',
  monitor: '#f7931d',
  deadspace_candidate: '#d71920',
  underperforming_facility: '#d71920',
  development_risk: '#f15c22',
  improvement_opportunity: '#f7931d',
  community_value_gap: '#d71920',
  strategic_learning: '#f15c22',
  intervened: '#2196f3',
}

const AUTHORITY_COLOR = { owned: '#3fb27f', sold: '#d71920', public: '#f7931d' } as const

const MODE: Record<InterventionMode, { icon: string; color: string; title: string }> = {
  direct: { icon: '●', color: '#d71920', title: 'Sime Darby owns this asset and can execute any intervention.' },
  collaborative: { icon: '◐', color: '#a855f7', title: 'Not SDP-owned, but a collaboration path exists (JMB, council, or the walkway around it).' },
  advisory: { icon: '○', color: '#7b7080', title: 'Not SDP-owned and no collaboration path. SDP can only recommend.' },
}

// Used by the analysis card below (its payload has its own units).
function fmt(v: number | null | undefined, unit: string) {
  if (v === null || v === undefined || Number.isNaN(v)) return '—'
  if (unit === 'ratio') return formatValue(v, 'ratio').text
  if (unit === 'RM') return formatValue(v, 'rm').text
  if (unit.startsWith('tCO2e')) return formatValue(v, 'tco2e').text
  return v.toLocaleString('en-US', { maximumFractionDigits: 2 })
}

function SectionTitle({ title, color = C.accent }: { title: string; color?: string }) {
  return (
    <div style={{ ...cap, fontSize: 11, color, borderBottom: `1px solid ${C.line}`, paddingBottom: 6, marginBottom: 10, marginTop: 24, letterSpacing: '0.05em' }}>
      {title}
    </div>
  )
}

function MetricLine({ m, lowerIsBetter }: { m: MainMetric; lowerIsBetter?: boolean }) {
  // "Counterfactual only" metrics carry `value` instead of baseline/intervention.
  const isSingleValue = m.value !== undefined && m.value !== null && m.baseline == null
  if (isSingleValue) {
    return (
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, padding: '6px 0', fontSize: 12.5 }}>
        <span style={{ color: '#cfc6cd' }}>{m.label}</span>
        {m.tier && <TierBadge tier={m.tier} />}
        <span style={{ ...mono, marginLeft: 'auto', fontWeight: 600, color: C.text }}>
          {fmt(m.value, m.unit)}
        </span>
      </div>
    )
  }

  const baselineMissing = m.baseline == null && m.intervention != null
  const moved = m.baseline != null && m.intervention != null && Math.abs(m.intervention - m.baseline) > 1e-9
  const better = moved && m.baseline != null && m.intervention != null
      ? (lowerIsBetter ? m.intervention < m.baseline : m.intervention > m.baseline)
      : null

  return (
    <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, padding: '6px 0', fontSize: 12.5 }}>
      <span style={{ color: '#cfc6cd' }}>{m.label}</span>
      {m.tier && <TierBadge tier={m.tier} />}
      <span style={{ ...mono, marginLeft: 'auto', color: C.faint }}>
        {baselineMissing || m.baseline == null ? 'n/a' : fmt(m.baseline, m.unit)}
      </span>
      <span style={{ color: C.faint }}>→</span>
      <span style={{ ...mono, fontWeight: 600, color: better === null ? C.text : better ? '#3fb27f' : '#d71920' }}>
        {fmt(m.intervention, m.unit)}
      </span>
    </div>
  )
}

/* ---------- Metric display ---------- */

function MetricRow({ m }: { m: ResolvedMetric }) {
  const f = formatMetric(m)
  return (
    <div className="metric-row" title={m.def.hint}>
      <span className="metric-label">{m.label}</span>
      <span className="metric-value" style={{ ...mono, color: m.unknown ? C.faint : isWarn(m) ? C.bad : C.text }}>
        {f.text}{f.unit && <span className="metric-unit">{f.unit}</span>}
      </span>
      <ServedTierBadge tier={m.tier} />
    </div>
  )
}

function CoreTile({ m }: { m: ResolvedMetric }) {
  const f = formatMetric(m)
  return (
    <div className="core-tile" title={m.def.hint}>
      <div className="core-tile-head">
        <span className="core-tile-label">{m.label}</span>
        <ServedTierBadge tier={m.tier} />
      </div>
      <div className="core-tile-value" style={{ ...mono, color: m.unknown ? C.faint : isWarn(m) ? C.bad : C.text }}>
        {f.text}{f.unit && <span className="metric-unit">{f.unit}</span>}
      </div>
    </div>
  )
}

function CoreMetrics({ asset }: { asset: Asset }) {
  const keys = coreMetricKeys(asset.assetType, authorityGroup(asset.profile))
  const metrics = keys.map((k) => resolveMetric(asset, k)).filter((m): m is ResolvedMetric => m !== null)
  if (metrics.length === 0) return null
  return <div className="core-grid">{metrics.map((m) => <CoreTile key={m.key} m={m} />)}</div>
}

/* ---------- Always visible: header + core + one-line diagnosis ---------- */

function AssetHeader({ asset, placement }: { asset: Asset; placement: Placement }) {
  const p = asset.profile
  const d = asset.diagnosis
  const group = authorityGroup(p)
  const status = d?.status ?? (asset.mapStatus as AssetStatus)
  const col = STATUS_COLOR[status] ?? C.muted
  const mode = d?.intervention_mode ? MODE[d.intervention_mode] : null
  const mix = p?.subunits?.length ?? 0
  const track = EVALUATION_TRACK[group]
  const top = diagnosisSummary(placement)
  const overrides = Object.values(asset.metricOverrides ?? {})
  const simYear = overrides[0]?.year
  const displayId = asset.id.startsWith('A-') ? asset.id.replace('A-', 'FAC-')
    : asset.id.startsWith('G-') ? asset.id.replace('G-', 'GRN-') : asset.id

  return (
    <div className="fade">
      <h2 style={{ margin: 0, fontSize: 21, fontWeight: 600, letterSpacing: '-0.01em' }}>{asset.name}</h2>
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'baseline', gap: '0 8px', marginTop: 4, fontSize: 12.5, color: C.faint }}>
        <span style={mono}>{displayId}</span>
        <span>· {assetTypeLabel(asset.assetType)}</span>
        {p?.identity.subtype && <span>· {subtypeLabel(p.identity.subtype)}</span>}
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 10 }}>
        {p?.authority && (
          <span className="pill" style={{ color: AUTHORITY_COLOR[group] }} title={track.why}>
            {AUTHORITY_GROUP_LABEL[group]}
          </span>
        )}
        {mode && d?.intervention_mode && (
          <span className="pill" style={{ color: mode.color }} title={mode.title}>
            {mode.icon} {modeLabel(d.intervention_mode)}
          </span>
        )}
        {mix > 1 && (
          <span className="pill" style={{ color: C.muted }} title="Unit mix from the asset register; details in the Tenancy tab">
            Mixed use · {mix} subtypes
          </span>
        )}
      </div>
      <div className="metric-note" style={{ marginTop: 6 }}>Evaluated on {track.label.toLowerCase()}</div>

      <div style={{ marginTop: 14 }}>
        <CoreMetrics asset={asset} />
      </div>

      <div className="diag-summary" title="Status, then the two highest-weighted flags">
        <span className="diag-dot" style={{ background: col }} />
        <span style={{ color: col, fontWeight: 600 }}>{statusLabel(status)}</span>
        {top.length > 0
          ? <span style={{ color: '#cfc6cd' }}>· {top.join(', ')}</span>
          : <span style={{ color: C.faint }}>· no flags raised</span>}
      </div>

      {asset.selectedYear != null && asset.diagnosisYear != null && asset.diagnosisYear !== asset.selectedYear && (
        <div className="metric-note" style={{ color: '#f7931d' }}>
          Showing the {asset.diagnosisYear} diagnosis: {asset.selectedYear} was not generated for this scenario.
        </div>
      )}
      {simYear != null && (
        <div className="metric-note">
          Values labelled simulated, estimated or assumed come from the {simYear} scenario; everything else is the 2026 baseline.
        </div>
      )}
    </div>
  )
}

/* ---------- Diagnosis tab: one list, flag + tier + weight, expandable ---------- */

function DiagnosisTab({ asset, placement, open, onToggle, onTenancy, color }: {
  asset: Asset
  placement: Placement
  open: Set<string>
  onToggle: (key: string) => void
  onTenancy: () => void
  color: string
}) {
  if (placement.flags.length === 0) {
    return <p className="metric-note">No flags raised for this asset in {asset.diagnosisYear ?? 2026}.</p>
  }
  return (
    <div>
      <div className="flag-head">
        <span>Flag</span><span>Weight</span>
      </div>
      {placement.flags.map((f) => {
        const key = `${asset.id}:${f.flag}`
        const isOpen = open.has(key)
        const hasDetail = f.evidence.length > 0 || f.seeTenancy || f.sharedWith.length > 0
        return (
          <div key={f.flag} className={`toggle-group${isOpen ? ' open' : ''}`}>
            <button
              className={`toggle flag-toggle${hasDetail ? '' : ' static'}`}
              onClick={() => hasDetail && onToggle(key)}
              aria-expanded={hasDetail ? isOpen : undefined}
            >
              <span className="toggle-chev" style={{ visibility: hasDetail ? 'visible' : 'hidden' }}>▸</span>
              <span className="toggle-title flag-label">{f.label}</span>
              {f.tier ? <TierBadge tier={f.tier} /> : <span />}
              <span className="flag-bar"><i style={{ width: `${Math.round(f.weight * 100)}%`, background: color }} /></span>
              <span className="flag-pct" style={mono}>{Math.round(f.weight * 100)}%</span>
            </button>
            {isOpen && (
              <div className="toggle-body">
                {f.evidence.map((m) => <MetricRow key={m.key} m={m} />)}
                {f.sharedWith.length > 0 && (
                  <div className="metric-note">
                    {f.evidence.length > 0 ? 'Other values are' : 'Values are'} shown under {f.sharedWith.join(', ')}.
                  </div>
                )}
                {f.seeTenancy && (
                  <button className="link-btn" onClick={onTenancy}>Per-subtype occupancy is in the Tenancy tab →</button>
                )}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

/* ---------- Metrics tab: four collapsible pillars ---------- */

function MetricsTab({ asset, placement }: { asset: Asset; placement: Placement }) {
  const env = asset.profile?.environmental
  const defaults = openPillars(asset.assetType)
  const any = PILLARS.some((p) => placement.pillars[p].length > 0)
  if (!any) return <p className="metric-note">No further metrics for this asset.</p>
  return (
    <>
      {PILLARS.map((pillar) => {
        const rows = placement.pillars[pillar]
        if (rows.length === 0) return null
        return (
          <details key={`${asset.id}-${pillar}`} className="toggle-group" open={defaults.has(pillar)}>
            <summary className="toggle">
              <span className="toggle-chev">▸</span>
              <span className="toggle-title">{pillar}</span>
              <span className="count-pill">{rows.length} {rows.length === 1 ? 'metric' : 'metrics'}</span>
            </summary>
            <div className="toggle-body">
              {rows.map((m) => <MetricRow key={m.key} m={m} />)}
              {pillar === 'Environmental' && env && (env.surface_temp_provenance || env.surface_temp_source_catalog) && (
                <div className="metric-note">
                  {[
                    env.surface_temp_provenance,
                    env.surface_temp_source_catalog,
                    env.surface_temp_period_start && env.surface_temp_period_end
                      ? `${env.surface_temp_period_start} to ${env.surface_temp_period_end}`
                      : null,
                  ].filter(Boolean).join(' · ')}
                </div>
              )}
            </div>
          </details>
        )
      })}
    </>
  )
}

/* ---------- Tenancy tab: subtype mix + external signals ---------- */

function SubtypeMix({ asset }: { asset: Asset }) {
  const subs = asset.profile?.subunits
  if (!subs || subs.length === 0) return null
  const tiers = asset.profile?.tiers
  // A column appears when at least one row has data for it.
  const cols = SUBUNIT_COLUMNS.filter((c) => subs.some((s) => s[c.field] != null))
  const th: React.CSSProperties = { paddingBottom: 4, fontWeight: 500, textAlign: 'right' }
  const td: React.CSSProperties = { padding: '5px 0', textAlign: 'right', ...mono }

  const cell = (s: Subunit, field: (typeof cols)[number]['field']) => {
    if (field === 'occupancy') {
      const v = s.occupancy
      return <span style={{ color: v != null && v < 0.4 ? C.bad : C.text }}>{formatValue(v, 'ratio').text}</span>
    }
    if (field === 'operational_count') {
      const dead = s.operational_count === 0
      return (
        <span style={{ color: s.operational_count == null ? C.faint : dead ? C.bad : '#3fb27f' }}>
          {s.operational_count ?? '—'} / {s.design_count ?? '—'}
        </span>
      )
    }
    return <span>{s.vitality_score != null ? formatValue(s.vitality_score, 'dec2').text : '—'}</span>
  }

  return (
    <>
      <div className="tab-subtitle">Subtype tenancy mix</div>
      <table style={{ width: '100%', fontSize: 11.5, borderCollapse: 'collapse' }}>
        <thead>
          <tr style={{ borderBottom: `1px solid ${C.line}`, color: C.muted, textAlign: 'left' }}>
            <th style={{ paddingBottom: 4, fontWeight: 500 }}>Subtype</th>
            <th style={th}>Area</th>
            {cols.map((c) => (
              <th key={c.field} style={th}>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
                  {c.label}
                  <ServedTierBadge tier={tiers?.[`subunits.${c.field}`]} />
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {subs.map((s) => (
            <tr key={s.subtype} style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
              <td style={{ padding: '5px 0', color: C.text }}>{subtypeLabel(s.subtype)}</td>
              <td style={{ ...td, color: C.muted }}>
                {formatValue(s.area_m2, 'area').text}<span className="metric-unit">m²</span>
              </td>
              {cols.map((c) => <td key={c.field} style={td}>{cell(s, c.field)}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="metric-note" style={{ fontStyle: 'italic' }}>
        {cols.map((c) => `${c.label}: ${c.note}`).join(' · ')}
      </div>
    </>
  )
}

function hasTenancy(asset: Asset): boolean {
  return (asset.profile?.subunits?.length ?? 0) > 0 || hasExternalSignals(asset)
}

/* ---------- Panel ---------- */

export function AssetPanel(props: {
  assets: Asset[]
  question: string
  setQuestion: (v: string) => void
  asked: string
  analysis: AnalyzeResult | null
  loading: boolean
  error: string | null
  onAsk: (files: File[]) => void
  previewing: boolean
  onPreview: () => void
  onClearPreview: () => void
  onSimulate: () => void
  onClose: () => void
  history: AnalyzeHistoryItem[]
  /** Selected tab; owned by App so it survives selecting another asset. */
  tab: PanelTab
  onTab: (t: PanelTab) => void
}) {
  const { assets, analysis, asked, error, previewing, history } = props
  const multi = assets.length > 1

  const [files, setFiles] = useState<File[]>([])
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [openFlags, setOpenFlags] = useState<Set<string>>(new Set())

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      const newFiles = Array.from(e.target.files)
      setFiles((prev) => [...prev, ...newFiles].slice(0, 3))
    }
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const removeFile = (index: number, e: React.MouseEvent) => {
    e.stopPropagation() // Prevent triggering the preview modal
    setFiles((prev) => prev.filter((_, i) => i !== index))
  }

  const handlePreviewFile = (file: File) => {
    if (file.type === 'application/pdf' || file.name.endsWith('.pdf')) {
      setPreviewUrl(URL.createObjectURL(file))
    } else {
      alert('Preview is currently optimized for PDF files.')
    }
  }

  const handleClosePreview = () => {
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl)
      setPreviewUrl(null)
    }
  }

  const toggleFlag = (key: string) =>
    setOpenFlags((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })

  const placements = new Map(assets.map((a) => [a.id, placeMetrics(a)]))
  const showTenancy = assets.some(hasTenancy)
  const tabs = PANEL_TABS.filter((t) => t.key !== 'tenancy' || showTenancy)
  // A remembered tab that is not available here (Tenancy without data, or the
  // old "Ask AI" tab) falls back to Diagnosis, without forgetting the choice.
  const tab: PanelTab = tabs.some((t) => t.key === props.tab) ? props.tab : 'diagnosis'

  // Bring a new answer (or error) into view, since it sits below the tab content.
  const answerRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (analysis || error) answerRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [analysis, error])

  const perAsset = (render: (a: Asset, pl: Placement) => React.ReactNode, filter?: (a: Asset) => boolean) =>
    assets.filter(filter ?? (() => true)).map((a) => (
      <div key={a.id} className="tab-asset">
        {multi && <div className="tab-asset-name">{a.name}</div>}
        {render(a, placements.get(a.id)!)}
      </div>
    ))

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {previewUrl && (
        <div
          onClick={handleClosePreview}
          style={{
            position: 'fixed', inset: 0, zIndex: 9999,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            background: 'rgba(20, 14, 19, 0.25)', backdropFilter: 'blur(1px)',
            padding: 40,
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="pop"
            style={{
              position: 'relative', background: '#fff',
              width: '100%', maxWidth: '650px', aspectRatio: '1 / 1.414', maxHeight: '90vh',
              borderRadius: 4, boxShadow: '0 24px 64px rgba(0,0,0,0.6)',
              overflow: 'hidden', display: 'flex', flexDirection: 'column',
            }}
          >
            <div style={{
              background: '#241c23', color: '#fff', padding: '10px 16px',
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              borderBottom: '1px solid #3d3140',
            }}>
              <span style={{ fontSize: 12, fontWeight: 600, letterSpacing: '.05em' }}>📄 Document Preview</span>
              <button onClick={handleClosePreview} style={{ background: 'none', border: 0, color: '#cfc6cd', fontSize: 20, cursor: 'pointer' }}>×</button>
            </div>
            <iframe
              src={`${previewUrl}#toolbar=0&navpanes=0&scrollbar=0`}
              style={{ flex: 1, border: 'none', width: '100%', height: '100%' }}
              title="PDF Preview"
            />
          </div>
        </div>
      )}

      <div className="fade" style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
        <span style={{ ...cap, fontSize: 10 }}>
          {multi ? `${assets.length} assets selected` : 'Selected asset'}
        </span>
        <span style={{ flex: 1 }} />
        <button className="ctrl" onClick={props.onClose} style={{ background: 'none', border: 0, color: C.muted, fontSize: 20, cursor: 'pointer', width: 30, height: 30, borderRadius: 6, lineHeight: 1, flex: 'none' }}>×</button>
      </div>

      <div className="panel-scroll">
        {assets.map((asset, idx) => (
          <div key={asset.id} style={{ marginTop: idx === 0 ? 2 : 26 }}>
            <AssetHeader asset={asset} placement={placements.get(asset.id)!} />
          </div>
        ))}

        <div className="tabs" role="tablist" style={{ gridTemplateColumns: `repeat(${tabs.length}, minmax(0, 1fr))` }}>
          {tabs.map((t) => (
            <button
              key={t.key}
              role="tab"
              aria-selected={tab === t.key}
              className={`tab${tab === t.key ? ' on' : ''}`}
              onClick={() => props.onTab(t.key)}
            >
              {t.label}
            </button>
          ))}
        </div>

        <div className="tab-body">
          {tab === 'diagnosis' && perAsset((a, pl) => {
            const d = a.diagnosis
            const col = STATUS_COLOR[(d?.status ?? a.mapStatus) as AssetStatus] ?? C.muted
            const acceptedItem = history.find((h) => h.status === 'accepted')
            const isPrimaryIntervened = acceptedItem?.result.interventions?.some((i) => i.target_asset_id === a.id && i.role === 'primary')
            const catalyticTargetId = analysis?.interventions?.find((i) => i.beneficiary_asset_id === a.id)?.target_asset_id
            return (
              <>
                {isPrimaryIntervened && (
                  <div className="callout" style={{ background: 'rgba(0,210,255,0.08)', borderColor: 'rgba(0,210,255,0.3)' }}>
                    <span style={{ fontSize: 11, color: '#00d2ff', fontWeight: 600 }}>Primary intervention active</span>
                    <p>This asset is undergoing the accepted plan's primary intervention.</p>
                  </div>
                )}
                {catalyticTargetId && (
                  <div className="callout" style={{ background: 'rgba(168,85,247,0.08)', borderColor: 'rgba(168,85,247,0.3)' }}>
                    <span style={{ fontSize: 11, color: '#a855f7', fontWeight: 600 }}>Catalytic beneficiary</span>
                    <p>This asset benefits from the intervention at <b>{catalyticTargetId}</b>.</p>
                  </div>
                )}
                <DiagnosisTab
                  asset={a} placement={pl} open={openFlags} onToggle={toggleFlag}
                  onTenancy={() => props.onTab('tenancy')} color={col}
                />
              </>
            )
          })}

          {tab === 'metrics' && perAsset((a, pl) => <MetricsTab asset={a} placement={pl} />)}

          {tab === 'tenancy' && perAsset((a, pl) => (
            <>
              <SubtypeMix asset={a} />
              <ExternalSignalsPanel asset={a} hidden={pl.claimed} />
            </>
          ), hasTenancy)}

        </div>

        {/* AI answer: in the scroll area, below the tab content and right above the ask bar. */}
        {(analysis || error) && (
          <div ref={answerRef} className="ai-answer">
            <div className="ai-answer-head">AI analysis</div>

        {error && (
          <div className="fade" style={{ padding: 14, marginBottom: 20, borderRadius: 8, background: 'rgba(215,25,32,0.1)', border: '1px solid rgba(215,25,32,0.3)', fontSize: 13, color: '#f0b8b8' }}>
            {error}
          </div>
        )}

        {analysis && (
          <div className="fade d3">
            <div style={{ ...cap, fontSize: 10, color: C.faint, marginBottom: 8 }}>Analysis Query</div>
            <p style={{ margin: '0 0 24px', fontSize: 14, fontStyle: 'italic', color: '#cfc6cd', lineHeight: 1.6 }}>“{asked}”</p>

            <SectionTitle title="AI Selected Plan" color="#3fb27f" />
            <div style={{ padding: 16, background: 'rgba(63,178,127,0.08)', border: `1px solid rgba(63,178,127,0.3)`, borderRadius: 8, marginBottom: 20 }}>
              <strong style={{ fontSize: 15, display: 'block', marginBottom: 8, color: '#fff' }}>{analysis.decision.selected_candidate}</strong>
              <p style={{ margin: 0, fontSize: 13, lineHeight: 1.65, color: '#cfc6cd' }}>{analysis.decision.reasoning}</p>
            </div>

            {analysis.decision.key_trade_offs?.length > 0 && (
              <div style={{ marginBottom: 24 }}>
                <div style={{ ...cap, fontSize: 10, color: C.muted, marginBottom: 10 }}>Key Trade-offs</div>
                <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, color: '#cfc6cd', lineHeight: 1.7 }}>
                  {analysis.decision.key_trade_offs.map((t) => <li key={t} style={{ marginBottom: 4 }}>{t}</li>)}
                </ul>
              </div>
            )}

            <SectionTitle title="Simulated Outcomes" color="#2196f3" />
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14, marginBottom: 24 }}>
              {analysis.assets_analysis.map((a) => {
                const card = a.summary_card
                const spec = a.engineering_spec
                const fin = card.financial?.main_metric
                const soc = card.social?.main_metric
                const env = card.environmental?.main_metrics ?? []
                const saved = card.financial?.counterfactual?.capex_saved_rm
                const averted = card.environmental?.counterfactual?.net_carbon_averted_tco2e

                return (
                  <div key={a.asset_id} style={{ padding: 16, background: C.card, border: `1px solid ${C.line}`, borderRadius: 8 }}>
                    <div style={{ ...mono, fontSize: 13, fontWeight: 600, marginBottom: 12, color: '#fff' }}>{a.asset_id}</div>


                    {/* Raw 2026 satellite reading, shown apart from the 2033 comparison so they aren't confused */}
                    {card.environmental?.observed_2026?.surface_temp_delta_c != null && (
                      <div style={{
                        padding: '6px 10px', marginBottom: 12, borderRadius: 6, fontSize: 11.5, color: '#cfc6cd',
                        background: 'rgba(33,150,243,0.08)', border: '1px solid rgba(33,150,243,0.25)',
                      }}>
                        <span style={{ color: '#2196f3', fontWeight: 600 }}>2026 OBSERVED</span>
                        {' · '}parcel {card.environmental.observed_2026.t_asset_c?.toFixed(1)} °C
                        {' · '}ΔT {card.environmental.observed_2026.surface_temp_delta_c.toFixed(2)} °C
                      </div>
                    )}

                    {/* P1 — Extracted engineering spec card */}
                    {spec && (
                      <div style={{
                        marginBottom: 14, padding: 12,
                        background: 'rgba(0,210,255,0.06)',
                        border: '1px solid rgba(0,210,255,0.25)',
                        borderRadius: 6,
                      }}>
                        <div style={{ ...cap, fontSize: 9.5, color: '#00d2ff', marginBottom: 8, letterSpacing: '.08em' }}>
                          ⚙️ ENGINEERED PARAM SPEC EXTRACTED
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px 16px', fontSize: 11.5 }}>
                          {spec.structure_retention_ratio !== null && (
                            <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: `1px dashed ${C.line}`, paddingBottom: 4 }}>
                              <span style={{ color: C.muted }}>Structure retained</span>
                              <span style={{ ...mono, color: '#fff', fontWeight: 600 }}>
                                {(spec.structure_retention_ratio * 100).toFixed(0)}%
                              </span>
                            </div>
                          )}
                          {spec.primary_material && (
                            <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: `1px dashed ${C.line}`, paddingBottom: 4 }}>
                              <span style={{ color: C.muted }}>Primary material</span>
                              <span style={{ ...mono, color: '#fff', fontWeight: 600 }}>
                                {humanize(spec.primary_material)}
                              </span>
                            </div>
                          )}
                          {spec.facade_action && spec.facade_action !== 'retain' && (
                            <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: `1px dashed ${C.line}`, paddingBottom: 4 }}>
                              <span style={{ color: C.muted }}>Facade</span>
                              <span style={{ ...mono, color: '#fff', fontWeight: 600 }}>
                                {humanize(spec.facade_action)}
                              </span>
                            </div>
                          )}
                          {spec.roof_intervention && spec.roof_intervention !== 'none' && (
                            <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: `1px dashed ${C.line}`, paddingBottom: 4 }}>
                              <span style={{ color: C.muted }}>Roof</span>
                              <span style={{ ...mono, color: '#fff', fontWeight: 600 }}>
                                {humanize(spec.roof_intervention)}
                              </span>
                            </div>
                          )}
                          {spec.hvac_cop !== null && (
                            <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: `1px dashed ${C.line}`, paddingBottom: 4 }}>
                              <span style={{ color: C.muted }}>HVAC COP</span>
                              <span style={{ ...mono, color: '#fff', fontWeight: 600 }}>
                                {spec.hvac_cop.toFixed(1)}
                              </span>
                            </div>
                          )}
                          {spec.operating_hours_per_week !== null && (
                            <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: `1px dashed ${C.line}`, paddingBottom: 4 }}>
                              <span style={{ color: C.muted }}>Op. hours/week</span>
                              <span style={{ ...mono, color: '#fff', fontWeight: 600 }}>
                                {spec.operating_hours_per_week.toFixed(0)}
                              </span>
                            </div>
                          )}
                          {spec.rooftop_pv_coverage !== null && spec.rooftop_pv_coverage > 0 && (
                            <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: `1px dashed ${C.line}`, paddingBottom: 4 }}>
                              <span style={{ color: C.muted }}>PV coverage</span>
                              <span style={{ ...mono, color: '#fff', fontWeight: 600 }}>
                                {(spec.rooftop_pv_coverage * 100).toFixed(0)}%
                              </span>
                            </div>
                          )}
                          {spec.pv_yield_kwh_year !== null && spec.pv_yield_kwh_year > 0 && (
                            <div style={{ display: 'flex', justifyContent: 'space-between', gridColumn: '1 / -1', borderBottom: `1px dashed ${C.line}`, paddingBottom: 4 }}>
                              <span style={{ color: C.muted }}>PV yield (annual)</span>
                              <span style={{ ...mono, color: '#00d2ff', fontWeight: 600 }}>
                                {Math.round(spec.pv_yield_kwh_year).toLocaleString()} kWh/yr
                              </span>
                            </div>
                          )}
                        </div>
                      </div>
                    )}

                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                      {fin && <MetricLine m={fin} />}
                      {soc && <MetricLine m={soc} />}
    
                      {env.map((m) => (
                        <div key={m.label}>
                          <MetricLine m={m} lowerIsBetter />
                          {m.cooling_source && m.cooling_source !== 'none' && (
                            <div style={{ fontSize: 10.5, color: C.faint, paddingLeft: 8, marginTop: -2, marginBottom: 4, fontStyle: 'italic' }}>
                              Cooling source: {humanize(m.cooling_source).toLowerCase()}
                              {m.cooling_from_roof_c != null && m.cooling_from_roof_c > 0 && (
                                <> · roof −{m.cooling_from_roof_c.toFixed(2)} °C</>
                              )}
                              {m.cooling_from_canopy_c != null && m.cooling_from_canopy_c < 0 && (
                                <> · canopy −{Math.abs(m.cooling_from_canopy_c).toFixed(2)} °C</>
                              )}
                            </div>
                          )}
                        </div>
                      ))}
                      
                    {card.subunits && card.subunits.length > 0 && (
                      <div style={{ marginTop: 14, paddingTop: 14, borderTop: `1px dashed ${C.line}` }}>
                        <div style={{ ...cap, fontSize: 10, color: C.accent, marginBottom: 8 }}>Subtype Breakdown</div>
                        <table style={{ width: '100%', fontSize: 11.5, borderCollapse: 'collapse' }}>
                          <thead>
                            <tr style={{ borderBottom: `1px solid ${C.line}`, color: C.muted, textAlign: 'left' }}>
                              <th style={{ paddingBottom: 4, fontWeight: 500 }}>Subtype</th>
                              <th style={{ paddingBottom: 4, fontWeight: 500, textAlign: 'right' }}>Area</th>
                              <th style={{ paddingBottom: 4, fontWeight: 500, textAlign: 'right' }}>Occ %</th>
                            </tr>
                          </thead>
                          <tbody>
                            {card.subunits.map((sub: any) => {
                              const isDead = sub.occupancy_intervention === 0;
                              return (
                                <tr key={sub.subtype} style={{ borderBottom: `1px solid rgba(255,255,255,0.05)` }}>
                                  <td style={{ padding: '6px 0', color: isDead ? C.faint : C.text }}>
                                    {subtypeLabel(sub.subtype)}
                                  </td>
                                  <td style={{ padding: '6px 0', textAlign: 'right', ...mono, color: C.muted }}>
                                    {sub.area_m2} m²
                                  </td>
                                  <td style={{ padding: '6px 0', textAlign: 'right', ...mono }}>
                                    <span style={{ color: isDead ? C.faint : C.text }}>{(sub.occupancy_baseline * 100).toFixed(0)}%</span>
                                    <span style={{ color: C.faint, margin: '0 4px' }}>→</span>
                                    <span style={{ 
                                      color: isDead ? C.faint : (sub.occupancy_intervention > sub.occupancy_baseline ? '#3fb27f' : C.text), 
                                      fontWeight: 600 
                                    }}>
                                      {isDead ? 'Removed' : `${(sub.occupancy_intervention * 100).toFixed(0)}%`}
                                    </span>
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    )}
                    </div>

                    {card.community && (
                      <div style={{
                        marginTop: 14, padding: 12,
                        background: 'rgba(247,147,29,.06)',
                        border: '1px solid rgba(247,147,29,.28)',
                        borderRadius: 6,
                      }}>
                        <div style={{ ...cap, fontSize: 9.5, color: '#f7931d', marginBottom: 8, letterSpacing: '.08em' }}>
                          📡 TIER 3A · OPERATIONAL PROXIES
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px 16px', fontSize: 11.5 }}>
                          {card.community.lbs?.unique_users?.baseline != null && (
                            <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: `1px dashed ${C.line}`, paddingBottom: 4 }}>
                              <span style={{ color: C.muted }}>LBS daily visitors</span>
                              <span style={{ ...mono, color: '#fff', fontWeight: 600 }}>
                                {Math.round(card.community.lbs.unique_users.baseline).toLocaleString()}
                                {card.community.lbs.unique_users.intervention != null && (
                                  <> → {Math.round(card.community.lbs.unique_users.intervention).toLocaleString()}</>
                                )}
                              </span>
                            </div>
                          )}
                          {card.community.lbs?.dwell_minutes != null && (
                            <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: `1px dashed ${C.line}`, paddingBottom: 4 }}>
                              <span style={{ color: C.muted }}>Avg dwell</span>
                              <span style={{ ...mono, color: '#fff', fontWeight: 600 }}>
                                {Math.round(card.community.lbs.dwell_minutes)} min
                              </span>
                            </div>
                          )}
                          {card.community.lbs?.flow_island_ratio != null && (
                            <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: `1px dashed ${C.line}`, paddingBottom: 4 }}>
                              <span style={{ color: C.muted }}>Flow-island ratio</span>
                              <span style={{ ...mono, color: card.community.lbs.flow_island_ratio < 0.30 ? '#d71920' : '#fff', fontWeight: 600 }}>
                                {card.community.lbs.flow_island_ratio.toFixed(2)}
                              </span>
                            </div>
                          )}
                          {card.community.business_presence_ratio != null && (
                            <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: `1px dashed ${C.line}`, paddingBottom: 4 }}>
                              <span style={{ color: C.muted }}>Business presence</span>
                              <span style={{ ...mono, color: '#fff', fontWeight: 600 }}>
                                {(card.community.business_presence_ratio * 100).toFixed(0)}%
                              </span>
                            </div>
                          )}
                          {card.community.business_turnover_count != null && (
                            <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: `1px dashed ${C.line}`, paddingBottom: 4 }}>
                              <span style={{ color: C.muted }}>Business turnover</span>
                              <span style={{ ...mono, color: '#fff', fontWeight: 600 }}>
                                {card.community.business_turnover_count} change(s)
                              </span>
                            </div>
                          )}
                          {card.community.lbs?.source && (
                            <div style={{ gridColumn: '1 / -1', fontSize: 10, color: C.faint, fontStyle: 'italic', marginTop: 4 }}>
                              Source: {card.community.lbs.source}
                            </div>
                          )}
                        </div>
                      </div>
                    )}

                    {card.counterfactual && card.counterfactual.metrics?.length > 0 && (
                      <div style={{
                        marginTop: 14, padding: 12,
                        background: 'rgba(123,112,128,.08)',
                        border: '1px solid rgba(123,112,128,.28)',
                        borderRadius: 6,
                      }}>
                        <div style={{ ...cap, fontSize: 9.5, color: '#a895a0', marginBottom: 8, letterSpacing: '.08em' }}>
                          🔮 {card.counterfactual.label.toUpperCase()}
                        </div>
                        <p style={{ margin: '0 0 6px', fontSize: 10, color: C.faint, fontStyle: 'italic' }}>
                          Not part of deadspace assessment. Shown for investment narrative only.
                        </p>
                        {card.counterfactual.metrics.map((m) => (
                          <MetricLine key={m.label} m={m as any} />
                        ))}
                      </div>
                    )}

                    {(saved !== undefined || averted !== undefined) && (
                      <div style={{ marginTop: 14, paddingTop: 14, borderTop: `1px dashed ${C.line}`, display: 'flex', flexDirection: 'column', gap: 8 }}>
                        {saved !== undefined && (
                          <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, fontSize: 13 }}>
                            <span style={{ color: C.muted }}>CAPEX avoided vs new build</span>
                            <span style={{ ...mono, marginLeft: 'auto', color: '#3fb27f', fontWeight: 600 }}>{fmt(saved, 'RM')}</span>
                          </div>
                        )}
                        {averted !== undefined && (
                          <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, fontSize: 13 }}>
                            <span style={{ color: C.muted }}>Embodied carbon averted</span>
                            <span style={{ ...mono, marginLeft: 'auto', color: '#3fb27f', fontWeight: 600 }}>{fmt(averted, 'tCO2e')} tCO₂e</span>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>

            <div style={{ padding: 16, background: 'rgba(255,255,255,0.03)', border: `1px solid ${C.line}`, borderRadius: 8, marginBottom: 16 }}>
              <div style={{ ...cap, fontSize: 10, color: C.accent, marginBottom: 6 }}>Recommendation</div>
              <p style={{ margin: 0, fontSize: 13, lineHeight: 1.65, color: '#cfc6cd' }}>{analysis.decision.justification.recommendation}</p>
              {analysis.decision.justification.beyond_the_model && (
                <p style={{ margin: '12px 0 0', fontSize: 12, lineHeight: 1.6, color: C.faint }}><b>Beyond model:</b> {analysis.decision.justification.beyond_the_model}</p>
              )}
            </div>

            <div style={{ display: 'flex', gap: 10, marginBottom: 24 }}>
              <button className="btn" onClick={() => (previewing ? props.onClearPreview() : props.onPreview())} style={btn()}>
                {previewing ? 'Clear map preview' : 'Preview on map'}
              </button>
              <button className="btn primary" onClick={props.onSimulate} style={btn(true)}>View Full Comparison</button>
            </div>
          </div>
        )}
          </div>
        )}
      </div>

      {/* Ask bar: a flex sibling of the scroll area, so it is always visible and never covers content. */}
      <div className="ask-bar">
        <label htmlFor="q" className="ask-label">
          <span>{analysis ? 'Ask a follow-up question' : multi ? `Ask AI about these ${assets.length} assets` : `Ask AI about ${assets[0].name}`}</span>
          {!multi && !analysis && (
            <span className="ask-hint">
              <kbd style={{ ...mono, fontSize: 9.5, padding: '1px 5px', borderRadius: 4, background: '#2b212a', border: `1px solid ${C.line}`, color: '#cfc6cd' }}>Ctrl</kbd>
              {' '}+ click to add assets
            </span>
          )}
        </label>

        {files.length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 10 }}>
            {files.map((f, i) => (
              <div 
                key={i} 
                onClick={() => handlePreviewFile(f)} // 🆕 ADDED: Click to preview
                style={{ 
                  display: 'flex', alignItems: 'center', gap: 6, 
                  background: 'rgba(247,147,29,.15)', border: '1px solid rgba(247,147,29,.3)',
                  padding: '4px 8px', borderRadius: 6, fontSize: 11, color: C.accent,
                  cursor: 'pointer', transition: 'background 0.2s'
                }}
                onMouseOver={(e) => e.currentTarget.style.background = 'rgba(247,147,29,.25)'}
                onMouseOut={(e) => e.currentTarget.style.background = 'rgba(247,147,29,.15)'}
                title="Click to preview document"
              >
                📎 {f.name}
                <button 
                  onClick={(e) => removeFile(i, e)} 
                  style={{ background: 'none', border: 0, color: C.accent, cursor: 'pointer', padding: 0, fontSize: 14, lineHeight: 1 }}
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        )}

        <div style={{ display: 'flex', gap: 8 }}>
          <input 
            type="file" 
            multiple 
            accept=".pdf" 
            ref={fileInputRef} 
            onChange={handleFileChange} 
            style={{ display: 'none' }} 
          />
          
          <button 
            className="btn" 
            onClick={() => fileInputRef.current?.click()}
            title="Attach PDF Document"
            style={{ ...btn(), padding: '0 14px', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 16 }}
          >
            📎
          </button>

          <input 
            id="q" 
            className="inp" 
            value={props.question} 
            onChange={(e) => props.setQuestion(e.target.value)} 
            onKeyDown={(e) => { if (e.key === 'Enter') props.onAsk(files) }}
            placeholder={analysis ? 'What if we prioritise environmental return?' : 'What should we do with these assets?'} 
            style={{ flex: 1, minWidth: 0, font: 'inherit', fontSize: 13, padding: '12px 14px', borderRadius: 8, border: `1px solid ${C.line}`, background: '#241c23', color: C.text }} 
          />
          
          <button 
            className={`btn primary${props.loading ? ' thinking' : ''}`} 
            onClick={() => props.onAsk(files)} 
            disabled={props.loading} 
            style={{ ...btn(true), padding: '0 20px' }}
          >
            {props.loading ? 'Thinking…' : 'Ask'}
          </button>
        </div>
      </div>
    </div>
  )
}
