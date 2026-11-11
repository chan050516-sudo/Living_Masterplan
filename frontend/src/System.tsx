import { useState } from 'react'
import type { CSSProperties } from 'react'
import './system.css'

// Sections that explain the current system: how it sees assets it does not
// own, who can act on a problem, and the soft interventions.
// Numbers come from the mock township (2026 snapshot).

type Signal = { name: string; source: string; tier: 'observed' | 'derived' | 'estimate'; value: string; usual: string; share?: number }
type Example = { id: string; tab: string; title: string; owner: string; signals: Signal[]; verdict: string }

const EXAMPLES: Example[] = [
  {
    id: 'BLD-0037',
    tab: 'A building Sime Darby owns',
    title: 'Supermarket',
    owner: 'Developer-owned, so its own records are used.',
    signals: [
      { name: 'Occupancy', source: 'Lease records', tier: 'observed', value: '64%', usual: 'below the usual for its type', share: 0.64 },
      { name: 'Empty for', source: 'Lease records', tier: 'observed', value: '14 months', usual: 'limit 12 months' },
      { name: 'Yearly income', source: 'Finance records', tier: 'observed', value: '− RM 1.19M', usual: 'costs more than it earns' },
      { name: 'Carbon spent on empty space', source: 'Energy model', tier: 'derived', value: '312 tCO₂e', usual: '36% of its yearly carbon', share: 0.36 },
    ],
    verdict: 'Deadspace candidate. Sime Darby can act directly.',
  },
  {
    id: 'BLD-0662',
    tab: 'A shop Sime Darby sold',
    title: 'Shoplot row',
    owner: 'Sold to an investor, so only outside signals are used.',
    signals: [
      { name: 'Daily visitors', source: 'Phone-location data', tier: 'estimate', value: '12', usual: 'usual for this type: 75', share: 12 / 75 },
      { name: 'Units open', source: 'Google Maps listings', tier: 'estimate', value: '0 of 5', usual: 'all closed', share: 0.02 },
      { name: 'Neighbours who can walk there', source: 'Street network', tier: 'derived', value: '38%', usual: 'cut off by a barrier', share: 0.38 },
    ],
    verdict: 'A flow island: people live nearby but can’t reach it. Sime Darby works with the owner.',
  },
]

const SOURCES = [
  { tier: 'observed', name: 'Its own records', text: 'Leases, occupancy and finances for the buildings Sime Darby still owns.' },
  { tier: 'estimate', name: 'Phone-location data', text: 'How many people visit each shop and how long they stay, bought from location-data providers.' },
  { tier: 'estimate', name: 'Google Maps listings', text: 'Which businesses are open or closed, their type, hours and ratings.' },
  { tier: 'observed', name: 'Satellite and maps', text: 'Building shapes, streets, tree cover and surface heat.' },
]

const MODES = [
  { key: 'direct', name: 'Direct', n: 66, text: 'Sime Darby still owns it and can act on its own.' },
  { key: 'collab', name: 'Collaborative', n: 75, text: 'Sold, but Sime Darby can help with the owner’s agreement.' },
  { key: 'advisory', name: 'Advisory', n: 109, text: 'Sold. Sime Darby can only advise, or learn for the next phase.' },
]

const QUESTIONS = [
  { q: 'Is it used?', a: 'Occupancy and vacancy for owned buildings. Open units and visitors for sold shops.' },
  { q: 'Does it give value back?', a: 'Income against costs for owned buildings. Estimated sales against the cost of staying open for sold shops.' },
]

const SOFT = [
  {
    name: 'Tenant matching',
    text: 'The system ranks which kind of business is most likely to survive in an empty shop: what the area is missing, how many rivals are nearby, and whether an anchor store draws people in. Sime Darby then connects the owner with that tenant.',
  },
  {
    name: 'Placemaking',
    text: 'A weekend market, night market or event nearby brings people back to the street. It lifts foot traffic for shops within about 400 m while it runs, then ends.',
  },
]

const WHY_SOFT = [
  { label: 'Owner needed?', hard: 'Must sell or rebuild', soft: 'Only has to agree' },
  { label: 'Cost', hard: 'Construction budget', soft: 'Matching and events' },
  { label: 'Time to see a change', hard: 'Years', soft: 'Months' },
]

export function DataSection() {
  const [pick, setPick] = useState(1)
  const ex = EXAMPLES[pick]
  return (
    <section className="lp-section sy-data" id="data">
      <p className="lp-kicker">Seeing what you don’t own</p>
      <h2>Most shops are sold. The system still sees how they are doing.</h2>
      <p className="lp-body">
        After a shop is sold, the developer can’t see its occupancy or income. So the system only uses data
        a developer can really get, and every number says where it came from.
      </p>
      <div className="sy-data-grid">
        <ul className="sy-sources rv">
          {SOURCES.map((s) => (
            <li key={s.name}>
              <i className={`sy-dot ${s.tier}`} />
              <div><h3>{s.name}</h3><p>{s.text}</p></div>
            </li>
          ))}
        </ul>
        <div className="sy-example rv">
          <div className="sy-tabs" role="tablist" aria-label="Example buildings">
            {EXAMPLES.map((e, i) => (
              <button key={e.id} role="tab" aria-selected={i === pick} className={i === pick ? 'on' : ''} onClick={() => setPick(i)}>{e.tab}</button>
            ))}
          </div>
          <article className="sy-card" key={ex.id} role="tabpanel">
            <p className="sy-card-id">{ex.id}</p>
            <h3>{ex.title}</h3>
            <p className="sy-card-owner">{ex.owner}</p>
            <ul>
              {ex.signals.map((s) => (
                <li key={s.name}>
                  <div className="sy-sig-head">
                    <span>{s.name}</span>
                    <strong>{s.value}</strong>
                  </div>
                  {s.share !== undefined && <div className="sy-bar"><i style={{ '--w': `${Math.max(s.share * 100, 2)}%` } as CSSProperties} /></div>}
                  <p className="sy-sig-foot"><i className={`sy-dot ${s.tier}`} />{s.source} · {s.usual}</p>
                </li>
              ))}
            </ul>
            <p className="sy-verdict">{ex.verdict}</p>
          </article>
        </div>
      </div>
    </section>
  )
}

export function AuthoritySection() {
  const total = MODES.reduce((s, m) => s + m.n, 0)
  return (
    <section className="sy-auth" id="who-acts">
      <div className="lp-inner">
        <p className="lp-kicker">Who can act</p>
        <h2>Deadspace is a fact. Ownership decides what you can do about it.</h2>
        <div className="sy-auth-grid">
          <div className="rv">
            <h3>Two questions for every building</h3>
            <ol className="sy-questions">
              {QUESTIONS.map((x, i) => (
                <li key={x.q}><span>{i + 1}</span><div><b>{x.q}</b><p>{x.a}</p></div></li>
              ))}
            </ol>
            <p className="sy-note">Both bad means deadspace. One bad sign alone means “watch it”. Signs that say the same thing are counted once.</p>
          </div>
          <div className="rv">
            <h3>Who can act on the {total} flagged assets</h3>
            <div className="sy-stack" role="img" aria-label={MODES.map((m) => `${m.name} ${m.n}`).join(', ')}>
              {MODES.map((m, i) => (
                <span key={m.key} className={m.key} style={{ flexGrow: m.n, '--d': `${i * 160}ms` } as CSSProperties} />
              ))}
            </div>
            <ul className="sy-modes">
              {MODES.map((m) => (
                <li key={m.key}>
                  <i className={m.key} />
                  <strong>{m.n}</strong>
                  <div><b>{m.name}</b><p>{m.text}</p></div>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </section>
  )
}

export function SoftSection() {
  return (
    <section className="lp-section lp-tinted sy-soft" id="soft">
      <div className="lp-inner">
        <p className="lp-kicker">Soft interventions</p>
        <h2>When you can’t rebuild a street, help it come back.</h2>
        <p className="lp-body">
          Shops in a township are sold to many separate investors. Each one leases to whoever pays most, nobody
          plans the street as a whole, and shops close one after another. Soft interventions work on sold shops,
          because the owner only has to agree.
        </p>
        <div className="sy-soft-grid">
          <div className="sy-soft-cards rv">
            {SOFT.map((s, i) => (
              <article key={s.name}>
                <span>{i + 1}</span>
                <h3>{s.name}</h3>
                <p>{s.text}</p>
              </article>
            ))}
          </div>
          <figure className="sy-sim rv">
            <figcaption>
              <b>BLD-0662, simulated</b>
              An empty sold shop, matched with a café
            </figcaption>
            <div className="sy-meter">
              <span>Before</span>
              <div className="sy-bar"><i className="muted" style={{ '--w': '3%' } as CSSProperties} /></div>
              <b>3%</b>
            </div>
            <div className="sy-meter">
              <span>After</span>
              <div className="sy-bar"><i style={{ '--w': '70%' } as CSSProperties} /></div>
              <b>70%</b>
            </div>
            <p className="sy-sim-label">Occupancy</p>
            <dl className="sy-sim-stats">
              <div><dt>Daily visitors</dt><dd>12 → <strong>293</strong></dd></div>
              <div><dt>Nearby shops still open</dt><dd>60% → <strong>63%</strong></dd></div>
            </dl>
            <table className="sy-why">
              <thead><tr><th scope="col"><span className="sr">Question</span></th><th scope="col">Rebuild</th><th scope="col">Soft</th></tr></thead>
              <tbody>
                {WHY_SOFT.map((w) => (
                  <tr key={w.label}><th scope="row">{w.label}</th><td>{w.hard}</td><td>{w.soft}</td></tr>
                ))}
              </tbody>
            </table>
          </figure>
        </div>
      </div>
    </section>
  )
}
