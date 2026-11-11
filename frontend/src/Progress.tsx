import { useState } from 'react'
import './progress.css'

// Mentoring-session progress section. Numbers come from the mock township
// on branch p2-p3-mock-data (11 Nov 2026).

const BEFORE_AFTER = [
  { from: '0.14', to: '0.95', label: 'How well foot-traffic data tracks real occupancy', note: 'correlation, checked on the mock' },
  { from: '916', to: '250', label: 'Assets flagged', note: 'a bug flagged every asset; target was 150–250' },
  { from: '58', to: '0', label: 'Sold shops wrongly shown empty in 2033', note: 'in the simulation' },
  { from: '464', to: '916', label: 'Buildings the simulation can place on the map', note: 'out of 916' },
]

type Step = {
  tag: string
  name: string
  found: string
  did: string[]
  result: { value: string; label: string }
  visual?: 'modes' | 'accuracy' | 'occupancy'
}

const STEPS: Step[] = [
  {
    tag: 'Phase 2',
    name: 'Honest detection',
    found: 'The system was reading the occupancy and income of shops Sime Darby had already sold. In real life a developer never sees that.',
    did: [
      'Sold assets are judged only on what a developer can see: phone-location foot traffic and Google business listings.',
      'New statuses for sold shops: community value gap (SDP can help) and strategic learning (a lesson for the next phase).',
      'Every flag says how sure it is: observed, derived or estimated.',
    ],
    result: { value: '61', label: 'deadspace candidates out of 916 assets' },
    visual: 'modes',
  },
  {
    tag: 'Phase 3',
    name: 'Realistic data',
    found: 'The foot-traffic data was copied from Google, the supermarket was marked as sold, and a bug counted unknown occupancy as 100% wasted carbon, so every asset was flagged.',
    did: [
      'Foot traffic is now counted per shop on a 100 m grid, the way real location-data providers sell it.',
      'Ownership follows real townships: Sime Darby keeps 66 of 916 assets, including the supermarket.',
      'Unknown stays unknown. It is never treated as empty.',
    ],
    result: { value: '0.95', label: 'foot-traffic accuracy (was 0.14)' },
    visual: 'accuracy',
  },
  {
    tag: 'Phase 5',
    name: 'AI that cites its sources',
    found: 'The AI only saw foot traffic and Google data hidden inside sentences, and did not know who owns each building.',
    did: [
      'The AI gets each signal as labelled data, with its source and how sure it is.',
      'It must say “phone data shows 12 visitors a day”, never “occupancy is 12%”.',
      'If two sources disagree, it says so and never averages them.',
    ],
    result: { value: '2 sources', label: 'phone foot traffic and Google listings, each labelled “estimate” for the AI' },
  },
  {
    tag: 'Review',
    name: 'Connecting the parts',
    found: 'We checked the links between the data, the AI and the simulation, and found 12 gaps. Sold shops dropped to 0% in future years, 452 buildings could not be found on the map, and the AI was told shops covered 1.98 million m² instead of 81,000.',
    did: [
      'Fixed 11 of the 12, each with an automated test.',
      'The 12th (a year-2027 counting rule) is explained and waiting for a team decision.',
    ],
    result: { value: '31', label: 'automated tests passing' },
  },
  {
    tag: 'New idea',
    name: 'Soft interventions',
    found: 'Most shoplots are sold to separate investors. Each leases to the highest bidder, nobody plans the street, and shops fail one after another.',
    did: [
      'Tenant matching: the system picks the business type most likely to survive in an empty shop.',
      'Placemaking: a market or event nearby brings people in while it runs.',
      'Both work on sold shops, because the owner only has to agree.',
    ],
    result: { value: '3% → 70%', label: 'occupancy of one empty shop after tenant matching (simulated)' },
    visual: 'occupancy',
  },
]

const MODES = [
  { key: 'direct', name: 'Direct', n: 66, text: 'Sime Darby can act' },
  { key: 'collab', name: 'Collaborative', n: 75, text: 'act with the owner' },
  { key: 'advisory', name: 'Advisory', n: 109, text: 'advise only' },
]

function Visual({ kind }: { kind: Step['visual'] }) {
  if (kind === 'modes') {
    const total = MODES.reduce((s, m) => s + m.n, 0)
    return (
      <figure className="pg-vis">
        <figcaption>Who can act on the 250 flagged assets</figcaption>
        <div className="pg-stack" role="img" aria-label={MODES.map((m) => `${m.name} ${m.n}`).join(', ')}>
          {MODES.map((m) => <span key={m.key} className={m.key} style={{ flexGrow: m.n }} title={`${m.name}: ${m.n}`} />)}
        </div>
        <ul className="pg-keys">
          {MODES.map((m) => (
            <li key={m.key}><i className={m.key} /><b>{m.n}</b> {m.name} <small>{m.text} · {Math.round((m.n / total) * 100)}%</small></li>
          ))}
        </ul>
      </figure>
    )
  }
  if (kind === 'accuracy') {
    return (
      <figure className="pg-vis">
        <figcaption>Foot-traffic data vs real occupancy (correlation)</figcaption>
        <Meter label="Before" value={0.14} text="0.14" muted />
        <Meter label="Now" value={0.95} text="0.95" />
      </figure>
    )
  }
  if (kind === 'occupancy') {
    return (
      <figure className="pg-vis">
        <figcaption>BLD-0662, an empty sold shop matched with a café</figcaption>
        <Meter label="Before" value={0.03} text="3%" muted />
        <Meter label="After" value={0.70} text="70%" />
        <p className="pg-vis-note">Daily visitors 12 → 293 · nearby shops still open 60% → 63%</p>
      </figure>
    )
  }
  return null
}

function Meter({ label, value, text, muted }: { label: string; value: number; text: string; muted?: boolean }) {
  return (
    <div className="pg-meter">
      <span>{label}</span>
      <div className="pg-track"><i className={muted ? 'muted' : ''} style={{ width: `${Math.max(value * 100, 1.5)}%` }} /></div>
      <b>{text}</b>
    </div>
  )
}

export function Progress() {
  const [on, setOn] = useState(0)
  const s = STEPS[on]
  return (
    <>
      <section className="pg" id="progress">
        <div className="lp-inner">
          <p className="lp-kicker">Progress since our last session</p>
          <h2>We rebuilt the data around what Sime Darby can actually see.</h2>
          <p className="lp-body">
            A developer can’t see the occupancy or income of a shop it has sold. So the system now judges
            sold assets from outside signals only, and every number says how sure it is.
          </p>

          <ul className="pg-ba rv">
            {BEFORE_AFTER.map((b) => (
              <li key={b.label}>
                <p className="pg-ba-num"><s>{b.from}</s><span aria-hidden="true">→</span><strong>{b.to}</strong></p>
                <p className="pg-ba-label">{b.label}</p>
                <small>{b.note}</small>
              </li>
            ))}
          </ul>

          <div className="pg-steps rv">
            <div className="pg-rail" role="tablist" aria-label="What we built, step by step">
              {STEPS.map((x, i) => (
                <button
                  key={x.name} role="tab" aria-selected={i === on}
                  className={i === on ? 'on' : i < on ? 'done' : ''}
                  onClick={() => setOn(i)}
                >
                  <span>{i + 1}</span>
                  <small>{x.tag}</small>
                  {x.name}
                </button>
              ))}
            </div>

            <article className="pg-card" key={on} role="tabpanel">
              <div className="pg-card-main">
                <p className="pg-tag">{s.tag}</p>
                <h3>{s.name}</h3>
                <p className="pg-found"><b>What we found</b>{s.found}</p>
                <div className="pg-did">
                  <b>What we did</b>
                  <ul>{s.did.map((d) => <li key={d}>{d}</li>)}</ul>
                </div>
              </div>
              <aside className="pg-card-side">
                <p className="pg-result"><strong>{s.result.value}</strong><span>{s.result.label}</span></p>
                <Visual kind={s.visual} />
              </aside>
            </article>
            <div className="pg-nav">
              <button onClick={() => setOn(Math.max(on - 1, 0))} disabled={on === 0}>← Previous</button>
              <button onClick={() => setOn(Math.min(on + 1, STEPS.length - 1))} disabled={on === STEPS.length - 1}>Next →</button>
            </div>
          </div>
          <p className="pg-foot">Business data is simulated on the real Bukit Jelutong layout. All numbers are from our mock township.</p>
        </div>
      </section>
    </>
  )
}
