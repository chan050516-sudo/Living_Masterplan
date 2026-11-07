import { useEffect, useRef, useState } from 'react'
import type { CSSProperties, PointerEvent } from 'react'

type Source = { cite: string; use: string; href?: string }
type Layer = { id: string; name: string; line: string; fact?: { value: string; label: string }; sources: Source[] }

// Listed bottom of the stack first.
const LAYERS: Layer[] = [
  {
    id: 'shapes',
    name: 'Building shapes',
    line: 'The physical township: what stands where.',
    sources: [{ cite: 'Microsoft. Global ML Building Footprints.', use: 'Building shapes.', href: 'https://github.com/microsoft/GlobalMLBuildingFootprints' }],
  },
  {
    id: 'network',
    name: 'Roads and paths',
    line: 'How people actually reach each place.',
    sources: [{ cite: 'OpenStreetMap contributors. Road, path and map data.', use: 'Walking and driving networks.', href: 'https://www.openstreetmap.org/copyright' }],
  },
  {
    id: 'carbon',
    name: 'Carbon',
    line: 'What each building locks in and burns each year.',
    fact: { value: '0.769', label: 'kgCO₂e per kWh, the 2022 Peninsular Malaysia grid factor' },
    sources: [
      { cite: 'CIDB Malaysia (2021). Embodied Carbon Inventory Data for Construction Materials.', use: 'Embodied carbon estimates.', href: 'https://www.cidb.gov.my/wp-content/uploads/2022/11/V4_EMBODIED-CARBON-INVENTORY-TEMPLATE-final-1.pdf' },
      { cite: 'Energy Commission of Malaysia (2026). Grid Emission Factor in Malaysia 2022–2024 (Provisional).', use: 'Operational carbon.', href: 'https://myenergystats.st.gov.my/documents/d/guest/grid-emission-factor-gef-in-malaysia-2022-2024-provisional-' },
    ],
  },
  {
    id: 'people',
    name: 'People and demand',
    line: 'Where people choose to go, and how much access really changes use.',
    fact: { value: '10% → 2.5%', label: 'a 10% change in access counts as a 2.5% change in use' },
    sources: [
      { cite: 'Huff, D. L. (1964). Defining and Estimating a Trading Area. Journal of Marketing, 28(4), 34–38.', use: 'Commercial demand allocation.' },
      { cite: 'Ewing, R. & Cervero, R. (2010). Travel and the Built Environment: A Meta-Analysis. Journal of the American Planning Association, 76(3), 265–294.', use: 'Why better access does not raise use one-to-one.', href: 'https://planning.org/knowledgebase/resource/9149498' },
      { cite: 'Cervero, R. (2002). Built Environments and Mode Choice: Toward a Normative Framework. Transportation Research Part D, 7(4), 265–284.', use: 'Link between built environment and travel choice.', href: 'https://worldtransitresearch.info/research/2102' },
    ],
  },
  {
    id: 'global',
    name: 'Why it matters',
    line: 'The global case for reusing before building.',
    fact: { value: '37%', label: 'of global emissions come from buildings and construction' },
    sources: [{ cite: 'UNEP & GlobalABC (2026). Global Status Report for Buildings and Construction 2025–2026.', use: 'Sector share of global emissions and material extraction.', href: 'https://www.unep.org/resources/report/global-status-report-buildings-and-construction-2025-2026' }],
  },
]

const CARBON_CELLS = [3, 7, 2, 9, 4, 1, 6, 8, 5, 2, 9, 3, 7, 1, 4, 6, 2, 8, 5, 9, 3, 6, 1, 7, 4, 8, 2, 5, 9, 3, 6, 1, 7, 2, 8, 4]

function Art({ id }: { id: string }) {
  if (id === 'shapes') return <img src="/landing/township-map.svg" alt="" />
  if (id === 'carbon') {
    return <div className="lp-ev-cells">{CARBON_CELLS.map((v, i) => <i key={i} style={{ opacity: v / 10 }} />)}</div>
  }
  return (
    <svg viewBox="0 0 300 300" fill="none" aria-hidden="true">
      {id === 'network' && (
        <g stroke="currentColor" strokeWidth="3" strokeLinecap="round">
          <path d="M-5 70C70 40 110 120 170 110S270 50 305 90" />
          <path d="M20 305C40 220 110 210 130 150S110 40 150-5" />
          <path d="M305 210C240 190 210 240 150 225S50 170-5 190" />
          <path d="M230 305C220 230 250 170 215 110S190 40 215-5" />
          <path d="M130 150C170 165 195 150 215 110" strokeDasharray="2 9" />
        </g>
      )}
      {id === 'people' && (
        <g stroke="currentColor" strokeWidth="2">
          <circle cx="150" cy="150" r="46" />
          <circle cx="150" cy="150" r="88" opacity=".65" />
          <circle cx="150" cy="150" r="130" opacity=".35" />
          <circle cx="150" cy="150" r="12" fill="currentColor" />
          <circle cx="72" cy="96" r="7" fill="currentColor" />
          <circle cx="226" cy="84" r="5" fill="currentColor" />
          <circle cx="212" cy="226" r="8" fill="currentColor" />
          <circle cx="88" cy="214" r="5" fill="currentColor" />
          <path d="M80 102 136 142M222 90 162 142M206 220 162 160M94 208 138 160" strokeDasharray="3 7" />
        </g>
      )}
      {id === 'global' && (
        <g stroke="currentColor" strokeWidth="2">
          <circle cx="150" cy="150" r="118" />
          <ellipse cx="150" cy="150" rx="52" ry="118" />
          <path d="M32 150h236M50 90h200M50 210h200M150 32v236" />
        </g>
      )}
    </svg>
  )
}

export function Evidence() {
  const [active, setActive] = useState(LAYERS.length - 1)
  const [held, setHeld] = useState(false)
  const [open, setOpen] = useState(false)
  const stage = useRef<HTMLDivElement>(null)
  const root = useRef<HTMLElement>(null)

  useEffect(() => {
    const el = root.current
    if (!el) return
    const io = new IntersectionObserver(([e]) => setOpen(e.isIntersecting), { threshold: 0.3 })
    io.observe(el)
    return () => io.disconnect()
  }, [])

  // Walks through the layers until the visitor picks one.
  useEffect(() => {
    if (held || !open || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    const t = setInterval(() => setActive((a) => (a + LAYERS.length - 1) % LAYERS.length), 3800)
    return () => clearInterval(t)
  }, [held, open])

  const pick = (i: number) => { setActive(i); setHeld(true) }

  const tilt = (e: PointerEvent<HTMLDivElement>) => {
    const r = e.currentTarget.getBoundingClientRect()
    stage.current?.style.setProperty('--tx', String((e.clientX - r.left) / r.width - 0.5))
    stage.current?.style.setProperty('--ty', String((e.clientY - r.top) / r.height - 0.5))
  }

  const layer = LAYERS[active]
  return (
    <section className={`lp-ev${open ? ' open' : ''}`} id="references" ref={root}>
      <div className="lp-inner">
        <p className="lp-kicker">References</p>
        <h2>What every number stands on</h2>
        <p className="lp-body">Pull the township apart, layer by layer. Pick one to see the sources behind it.</p>
        <div className="lp-ev-grid">
          <div className="lp-ev-view" onPointerMove={tilt}>
            <div className="lp-ev-stack" ref={stage}>
              {LAYERS.map((l, i) => (
                <div
                  key={l.id}
                  className={`lp-ev-plate ${l.id}${i === active ? ' on' : ''}`}
                  style={{ '--i': i } as CSSProperties}
                  onPointerEnter={(e) => { if (e.pointerType === 'mouse') pick(i) }}
                  onClick={() => pick(i)}
                >
                  <Art id={l.id} />
                  <span>{l.name}</span>
                </div>
              ))}
            </div>
          </div>
          <div>
            <div className="lp-ev-tabs" role="tablist" aria-label="Evidence layers">
              {LAYERS.map((l, i) => ({ l, i })).reverse().map(({ l, i }) => (
                <button key={l.id} role="tab" aria-selected={i === active} className={i === active ? 'on' : ''} onClick={() => pick(i)}>
                  {l.name}
                </button>
              ))}
            </div>
            <div className="lp-ev-card" key={layer.id} role="tabpanel">
              <h3>{layer.name}</h3>
              <p>{layer.line}</p>
              {layer.fact && (
                <div className="lp-ev-fact">
                  <strong>{layer.fact.value}</strong>
                  <span>{layer.fact.label}</span>
                </div>
              )}
              <ul>
                {layer.sources.map((s) => (
                  <li key={s.cite}>
                    {s.href ? <a href={s.href} target="_blank" rel="noreferrer">{s.cite}</a> : <span>{s.cite}</span>}
                    <small>{s.use}</small>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
