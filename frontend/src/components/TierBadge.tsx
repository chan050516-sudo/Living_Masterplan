import type { DataTier, ServedTier } from '../types'

// Tier labels and colours. Kept in the original compact T1/T2/3A/3B style.
const TIER_CONFIG: Record<string, { label: string; color: string; title: string }> = {
  '1':  { label: 'T1', color: '#2196f3', title: 'Observed: direct record or measurement' },
  '2':  { label: 'T2', color: '#ecaa00', title: 'Derived: physics or economic formula on observed data' },
  '3a': { label: '3A', color: '#a855f7', title: 'Operational estimate: external proxy, valid for deadspace judgement' },
  '3b': { label: '3B', color: '#7b7080', title: 'Counterfactual: simulation narrative only' },
  U:    { label: 'U',  color: '#8a7f8c', title: 'Unknown: no defensible source for this asset' },
}

/** Shown in every badge's tooltip (replaces the legend line in the panel). */
const TIER_LEGEND = 'Data tiers: T1 observed · T2 derived · 3A estimate (proxy) · 3B counterfactual · U unknown'

export function TierBadge({ tier, source, mock }: { tier: DataTier | ServedTier['tier']; source?: string | null; mock?: boolean }) {
  const cfg = TIER_CONFIG[String(tier)]
  if (!cfg) return null
  const title = [
    cfg.title,
    source ? `Source: ${source.replace(/_/g, ' ')}` : null,
    mock ? 'Synthetic demo data on the real product schema' : null,
    '',
    TIER_LEGEND,
  ].filter((l) => l !== null).join('\n')
  return (
    <span
      className="tier-badge"
      title={title}
      style={{
        fontSize: 9,
        lineHeight: '13px',
        padding: '0 5px',
        borderRadius: 3,
        background: `${cfg.color}22`,
        color: cfg.color,
        border: `1px solid ${cfg.color}55`,
        fontWeight: 700,
        letterSpacing: '0.05em',
        cursor: 'help',
        flexShrink: 0,
        minWidth: 22,
        textAlign: 'center',
      }}
    >
      {cfg.label}
    </span>
  )
}

/** Badge for a served tier entry (profile.tiers[path]). */
export function ServedTierBadge({ tier }: { tier?: ServedTier }) {
  if (!tier) return null
  return <TierBadge tier={tier.tier} source={tier.source} mock={tier.mock} />
}
