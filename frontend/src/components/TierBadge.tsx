import { C } from '../theme'

export type Tier = '1' | '2' | '3a' | '3b' | 'U'

// How trustworthy a number is, per the data foundation plan's tier system.
const TIER: Record<Tier, { label: string; colour: string; hint: string }> = {
  '1':  { label: 'Observed',       colour: '#3fb27f', hint: 'Sime Darby record or direct measurement' },
  '2':  { label: 'Derived',        colour: '#2196f3', hint: 'Calculated from observed data' },
  '3a': { label: 'Estimate',       colour: '#f7931d', hint: 'Proxy from external data, valid for diagnosis' },
  '3b': { label: 'Counterfactual', colour: '#a855f7', hint: 'What it would be if Sime Darby had retained it' },
  U:    { label: 'Unknown',        colour: C.faint,   hint: 'No defensible source' },
}

export function TierBadge({ tier, mock }: { tier: Tier; mock?: boolean }) {
  const t = TIER[tier]
  return (
    <span
      title={t.hint + (mock ? '. Synthetic data built on the real product schema.' : '')}
      style={{
        fontSize: 9.5, letterSpacing: '.06em', textTransform: 'uppercase', fontWeight: 600,
        color: t.colour, border: `1px solid ${t.colour}55`, background: `${t.colour}14`,
        borderRadius: 4, padding: '1px 5px', whiteSpace: 'nowrap', flex: 'none',
      }}
    >
      {t.label}{mock ? ' · mock' : ''}
    </span>
  )
}