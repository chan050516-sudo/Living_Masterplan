import type { DataTier } from '../types'

const TIER_CONFIG: Record<string, { label: string; color: string; title: string }> = {
  '1':  { label: 'T1', color: '#2196f3', title: 'Observed — direct record' },
  '2':  { label: 'T2', color: '#ecaa00', title: 'Derived — physics or economic formula' },
  '3a': { label: '3A', color: '#a855f7', title: 'Operational estimate — proxy valid for deadspace judgement' },
  '3b': { label: '3B', color: '#7b7080', title: 'Counterfactual — simulation narrative only' },
}

export function TierBadge({ tier, source }: { tier: DataTier; source?: string }) {
  const key = String(tier)
  const cfg = TIER_CONFIG[key]
  if (!cfg) return null
  return (
    <span
      title={source ? `${cfg.title} · source: ${source}` : cfg.title}
      style={{
        fontSize: 9,
        padding: '1px 5px',
        borderRadius: 3,
        background: `${cfg.color}22`,
        color: cfg.color,
        border: `1px solid ${cfg.color}55`,
        marginLeft: 6,
        fontWeight: 700,
        letterSpacing: '0.05em',
        cursor: 'help',
        flexShrink: 0,
      }}
    >
      {cfg.label}
    </span>
  )
}