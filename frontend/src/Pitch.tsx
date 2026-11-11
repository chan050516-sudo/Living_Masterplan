import type { CSSProperties } from 'react'
import './pitch.css'

// Sections that follow the pitch flow: problem, what makes it different,
// feasibility, impact and the closing value proposition.

const DEMO_HREF = '#/demo'

const PROBLEM_FACTS = [
  { value: '850', of: 'of 916', label: 'assets Sime Darby no longer runs: sold to investors or handed over' },
  { value: '250', of: 'of 916', label: 'assets already showing a problem' },
  { value: '61', of: '', label: 'clear deadspace: empty or not giving value back' },
  { value: '37%', of: '', label: 'of global emissions come from buildings and construction' },
]

const CHAIN = [
  'A shop is sold to an investor',
  'It is leased to whoever pays most',
  'Nobody plans the street as a whole',
  'Shops close one after another',
  'Empty buildings still cost money and carbon',
]

const DIFFERENT = [
  { name: 'It sees what you don’t own', text: 'Sold shops are judged from outside signals anyone can buy, not from records a developer will never get.' },
  { name: 'Every number is honest', text: 'Each number says where it came from and how sure it is. The AI cites the source and never invents figures.' },
  { name: 'It has options for sold shops', text: 'Soft interventions like tenant matching and markets need only the owner’s agreement, not a rebuild.' },
  { name: 'It tests before you spend', text: 'Every plan runs through the same simulation out to 2033 before any money is committed.' },
]

const ROLLOUT = [
  { when: 'Month 1', name: 'Connect the data', text: 'Load the records Sime Darby already has for the buildings it owns, and subscribe to foot-traffic data and Google Maps listings for the rest.' },
  { when: 'Month 2', name: 'Run the township check', text: 'The system flags what needs attention and says who can act on each one.' },
  { when: 'Month 3', name: 'Pilot one street', text: 'Pick one struggling shop row. Match tenants and run a weekend market with the owners’ agreement.' },
  { when: 'Month 6', name: 'Measure and repeat', text: 'The same data shows whether visitors and open shops went up. Then move to the next street.' },
]

const NEEDS = [
  'No new sensors or surveys',
  'Data Sime Darby already has, or can buy',
  'One standard data format for any township',
  'Runs in the cloud, opened in a browser',
]

const IMPACT = [
  { who: 'Sime Darby', change: 'Sees every asset, owned or sold, and spends capital only on plans that worked in the simulation.' },
  { who: 'Shop owners', change: 'Get matched with tenants who are more likely to stay, so their shops fill again.' },
  { who: 'Residents', change: 'Get back the shops and services they need, close to home and reachable on foot.' },
  { who: 'Planet', change: 'Reusing buildings keeps their embodied carbon in place, and less energy is spent on empty space.' },
]

export function ProblemSection() {
  return (
    <section className="pt-problem" id="problem">
      <div className="lp-inner">
        <p className="lp-kicker"><span className="pt-num">01</span>The problem</p>
        <h2>Townships are built once, then sold piece by piece. Nobody watches what slowly dies.</h2>
        <p className="lp-body">
          After handover, the developer loses sight of most of the township. Shops struggle quietly, streets lose
          their life, and empty buildings keep costing money and carbon. By the time anyone notices, the fix is a
          rebuild.
        </p>
        <ul className="pt-facts rv">
          {PROBLEM_FACTS.map((f, i) => (
            <li key={f.label} style={{ '--d': `${i * 110}ms` } as CSSProperties}>
              <strong>{f.value}<small>{f.of}</small></strong>
              <span>{f.label}</span>
            </li>
          ))}
        </ul>
        <ol className="pt-chain rv" aria-label="How a street dies">
          {CHAIN.map((c, i) => (
            <li key={c} style={{ '--d': `${300 + i * 160}ms` } as CSSProperties}><span>{i + 1}</span>{c}</li>
          ))}
        </ol>
        <p className="pt-src">Township figures: our Bukit Jelutong model. Global figure: UNEP &amp; GlobalABC, 2026.</p>
      </div>
    </section>
  )
}

export function DifferentSection() {
  return (
    <section className="lp-section pt-diff" id="different">
      <p className="lp-kicker">What makes it different</p>
      <h2>Not another dashboard. A way to act on assets you no longer control.</h2>
      <ol className="pt-diff-grid rv">
        {DIFFERENT.map((d, i) => (
          <li key={d.name} style={{ '--d': `${i * 90}ms` } as CSSProperties}>
            <span>{String(i + 1).padStart(2, '0')}</span>
            <h3>{d.name}</h3>
            <p>{d.text}</p>
          </li>
        ))}
      </ol>
    </section>
  )
}

export function FeasibilitySection() {
  return (
    <section className="pt-feas" id="feasibility">
      <div className="lp-inner">
        <p className="lp-kicker"><span className="pt-num">04</span>Feasibility</p>
        <h2>How Sime Darby could start using it this year</h2>
        <div className="pt-feas-grid">
          <ol className="pt-roll rv">
            {ROLLOUT.map((r) => (
              <li key={r.name}>
                <b>{r.when}</b>
                <div><h3>{r.name}</h3><p>{r.text}</p></div>
              </li>
            ))}
          </ol>
          <div className="pt-needs rv">
            <h3>What it needs</h3>
            <ul>{NEEDS.map((n) => <li key={n}>{n}</li>)}</ul>
            <h3 className="pt-scale">Works across townships</h3>
            <p>
              There is no fixed database. Any township connects its own buildings, leases and outside signals through
              the same format, and the same rules and models run on it. Bukit Jelutong is our test case.
            </p>
          </div>
        </div>
      </div>
    </section>
  )
}

export function ImpactSection() {
  return (
    <section className="lp-section" id="impact">
      <p className="lp-kicker"><span className="pt-num">04</span>Impact</p>
      <h2>Who benefits, and what changes</h2>
      <div className="pt-impact rv">
        {IMPACT.map((v, i) => (
          <article key={v.who} style={{ '--d': `${i * 90}ms` } as CSSProperties}>
            <h3>{v.who}</h3>
            <p>{v.change}</p>
          </article>
        ))}
      </div>
    </section>
  )
}

export function ClosingSection() {
  return (
    <section className="pt-close" id="value">
      <div className="lp-inner">
        <p className="lp-kicker"><span className="pt-num">05</span>Why it matters</p>
        <h2>Don’t just build greener. <em>Build only what the future still needs.</em></h2>
        <p className="lp-body">
          Living Masterplan finds what a township has stopped using, even after it is sold, and tests the cheapest
          way to bring it back before a single ringgit is spent.
        </p>
        <a className="lp-cta" href={DEMO_HREF}>Launch demo</a>
      </div>
    </section>
  )
}
