export const C = {
  bg: '#2b212a',
  panel: '#332832',
  card: '#271e26',
  line: '#473b46',
  text: '#f2eef1',
  muted: '#99a5c0',
  faint: '#7b7080',
  accent: '#f7931d',
  bad: '#d71920',
  warn: '#ecaa00',
  good: '#43a047',
  selected: '#2196f3',
  intervene: '#2196f3',
  spill: '#a855f7',
  context: '#5f5566',
} as const

export const tierColor = { observed: C.intervene, estimated: C.warn, scenario: C.bad } as const

export const scoreColor = (field: string) =>
  ['step', ['get', field], C.bad, 40, C.warn, 60, C.good] as unknown as never

export const bandColor = (s: number) => (s < 40 ? C.bad : s < 60 ? C.warn : C.good)

export const btn = (active = false): React.CSSProperties => ({
  padding: '7px 16px',
  borderRadius: 6,
  border: `1px solid ${active ? C.accent : C.line}`,
  background: active ? C.accent : 'transparent',
  color: active ? '#1a1419' : '#cfc6cd',
  cursor: 'pointer',
  fontSize: 13,
  fontWeight: active ? 700 : 400,
  fontFamily: 'inherit',
})

export const cap: React.CSSProperties = {
  fontSize: 11,
  letterSpacing: '.14em',
  textTransform: 'uppercase',
  color: C.muted,
  fontWeight: 600,
}

export const mono: React.CSSProperties = {
  fontFamily: 'ui-monospace, monospace',
  fontVariantNumeric: 'tabular-nums',
}