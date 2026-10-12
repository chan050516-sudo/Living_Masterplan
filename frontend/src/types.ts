export type Tier = 'observed' | 'estimated' | 'scenario'

export type Factor = { label: string; weight: number }
export type Evidence = { label: string; value: string; tier: Tier }
export type Breakdown = { financial: number; environmental: number; social: number }

export type Asset = {
  id: string
  name: string
  type: string
  status: string
  center: [number, number]
  score: number
  occupancy: number
  vacancy_months: number
  score_3y: number
  occupancy_3y: number
  breakdown: Breakdown
  breakdown_3y: Breakdown
  factors: Factor[]
  evidence: Evidence[]
}

export type AiOption = {
  id: string
  title: string
  summary: string
  capex: string
  score_after: number
  carbon_avoided: string
  changes: string[]
  spillover: string[]
}

export type AiAnswer = { asked: string; analysis: string; options: AiOption[] }

export type ComparisonRow = {
  label: string
  current: string
  a: string
  b: string
  c: string
  best?: 'current' | 'a' | 'b' | 'c'
  key?: boolean
  delta?: boolean
}

export type Comparison = { rows: ComparisonRow[]; recommended: string; reason: string }