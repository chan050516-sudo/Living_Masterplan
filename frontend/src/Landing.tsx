import './landing.css'

const DEMO_HREF = '#/demo'

// Prototype snapshot from GET /api/assets/profiles. Refresh before submission.
const HEADLINE = [
  { value: '916', label: 'assets analysed' },
  { value: '81', label: 'deadspace candidates' },
  { value: '31,011', label: 'tCO₂e a year stranded' },
  { value: '5 years', label: 'simulated for every plan' },
]

const DEADSPACE_COSTS = [
  { name: 'Financial', text: 'Rental losses and maintenance keep building up on idle floor space.' },
  { name: 'Environmental', text: 'Energy cools and lights empty floors, while the carbon in the structure gives nothing back.' },
  { name: 'Social', text: 'Long vacancies leave residents with fewer useful places within walking distance.' },
]

const STEPS = [
  {
    name: 'Audit',
    what: 'Reads every asset’s occupancy, leases, finances, carbon and walking access.',
    example: 'A 4,809 m² supermarket loses RM 1.19M a year. 36% of its operational carbon, 312 tCO₂e a year, is stranded.',
  },
  {
    name: 'Diagnose',
    what: 'Clear rules raise named flags. There is no single black-box score.',
    example: 'Flagged as a deadspace candidate: five years below benchmark, negative income and 14 months of vacancy.',
  },
  {
    name: 'Generate',
    what: 'The AI proposes 2–3 plans inside the budget, leases and rules.',
    example: 'With RM 3M and no demolition, it tries an office hub, an energy retrofit and a showroom with walkway upgrades.',
  },
  {
    name: 'Simulate',
    what: 'Every valid plan runs through the same five-year model.',
    example: 'The reuse plans avoid about 2,020 tCO₂e of embodied carbon compared with building new.',
  },
  {
    name: 'Decide',
    what: 'The AI reads the simulated results, picks a plan and states the trade-offs.',
    example: 'It picks the office hub, and states that the showroom would cut more carbon.',
  },
]

const CONCEPTS = [
  { term: 'Deadspace', text: 'A building or space that cost money and carbon to create, but no longer gives enough value back.' },
  { term: 'Stranded carbon', text: 'The operational carbon spent on capacity nobody is using, such as cooling an empty floor.' },
  { term: 'Embodied carbon', text: 'The carbon already locked into a building by making and moving its materials.' },
  { term: 'Avoided embodied carbon', text: 'The carbon saved by reusing a structure: the new-build figure minus the reuse figure.' },
  { term: 'Urban heat island', text: 'Built-up areas become hotter than their surroundings. Tree canopy helps cool them.' },
  { term: 'Huff model', text: 'Estimates where people will choose to shop, based on how large each place is and how far away it is.' },
  { term: 'Catalytic project', text: 'A project on one asset that also lifts the assets around it.' },
  { term: 'Adaptive reuse', text: 'Changing how an existing building is used, instead of demolishing it and building again.' },
]

const TIERS = [
  { name: 'Observed', tier: 'observed', text: 'Comes directly from the township’s data.' },
  { name: 'Estimated', tier: 'estimated', text: 'Calculated from that data using a model or benchmark.' },
  { name: 'Scenario', tier: 'scenario', text: 'A simulated future, not a promise.' },
]

const RULES = [
  'The AI never calculates the numbers. It reads them from the tools.',
  'A plan that breaks the budget or lease rules is rejected before simulation.',
  'If a claimed benefit does not appear in the simulation, the claim is downgraded automatically.',
]

const IMPACT = [
  { who: 'Planet', text: 'Keeps embodied carbon in existing structures, reduces material extraction and finds carbon wasted on unused space.' },
  { who: 'SDP', text: 'Compares reuse, improve and build options before capital is committed, with the reasoning written down.' },
  { who: 'Residents', text: 'Turns idle space into what the neighbourhood needs, closer to home and easier to reach on foot.' },
]

const REFERENCES = [
  {
    cite: 'UNEP & GlobalABC (2026). Global Status Report for Buildings and Construction 2025–2026.',
    use: 'Sector share of global emissions and material extraction.',
    href: 'https://www.unep.org/resources/report/global-status-report-buildings-and-construction-2025-2026',
  },
  {
    cite: 'CIDB Malaysia (2021). Embodied Carbon Inventory Data for Construction Materials.',
    use: 'Embodied carbon estimates.',
    href: 'https://www.cidb.gov.my/wp-content/uploads/2022/11/V4_EMBODIED-CARBON-INVENTORY-TEMPLATE-final-1.pdf',
  },
  {
    cite: 'Energy Commission of Malaysia (2026). Grid Emission Factor in Malaysia 2022–2024 (Provisional).',
    use: 'Operational carbon: 0.769 kgCO₂e/kWh, the 2022 Peninsular Malaysia factor.',
    href: 'https://myenergystats.st.gov.my/documents/d/guest/grid-emission-factor-gef-in-malaysia-2022-2024-provisional-',
  },
  {
    cite: 'Ewing, R. & Cervero, R. (2010). Travel and the Built Environment: A Meta-Analysis. Journal of the American Planning Association, 76(3), 265–294.',
    use: 'Why better access does not raise use one-to-one.',
    href: 'https://planning.org/knowledgebase/resource/9149498',
  },
  {
    cite: 'Cervero, R. (2002). Built Environments and Mode Choice: Toward a Normative Framework. Transportation Research Part D, 7(4), 265–284.',
    use: 'Link between built environment and travel choice.',
    href: 'https://worldtransitresearch.info/research/2102',
  },
  {
    cite: 'Huff, D. L. (1964). Defining and Estimating a Trading Area. Journal of Marketing, 28(4), 34–38.',
    use: 'Commercial demand allocation.',
  },
  {
    cite: 'OpenStreetMap contributors. Road, path and map data.',
    use: 'Walking and driving networks.',
    href: 'https://www.openstreetmap.org/copyright',
  },
  {
    cite: 'Microsoft. Global ML Building Footprints.',
    use: 'Building shapes.',
    href: 'https://github.com/microsoft/GlobalMLBuildingFootprints',
  },
]

const TEAM = ['David', 'Hanan', 'Mathaba', 'Shimaa', 'Yu Qian']

export function Landing() {
  return (
    <div className="lp">
      <nav className="lp-nav" aria-label="Main">
        <a className="lp-brand" href="#top">LIVING MASTERPLAN</a>
        <div className="lp-links">
          <a href="#how">How it works</a>
          <a href="#concepts">Concepts</a>
          <a href="#trust">Evidence</a>
          <a href="#references">References</a>
        </div>
        <a className="lp-cta small" href={DEMO_HREF}>Launch demo</a>
      </nav>

      <header className="lp-hero" id="top">
        <div className="lp-hero-text">
          <p className="lp-eyebrow">Township of Tomorrow Hackathon 2026 · Planet track</p>
          <h1>Don’t just build greener. Build only what the future still needs.</h1>
          <p className="lp-lede">
            Living Masterplan finds township assets that have stopped giving value back, then tests
            whether to reuse, improve or build, five years ahead, before anyone adds new carbon.
          </p>
          <div className="lp-hero-actions">
            <a className="lp-cta" href={DEMO_HREF}>Launch demo</a>
            <a className="lp-quiet" href="#how">See how it works</a>
          </div>
        </div>
        <figure className="lp-hero-map">
          <img src="/landing/township-map.svg" width="1020" height="1010" alt="Building footprints of Bukit Jelutong, with deadspace candidates highlighted in orange and assets to watch in pale grey." />
          <figcaption>
            <span><i className="ok" />Healthy</span>
            <span><i className="watch" />Watch</span>
            <span><i className="dead" />Deadspace candidate</span>
          </figcaption>
        </figure>
        <div className="lp-stats">
          {HEADLINE.map((s) => (
            <div key={s.label}>
              <strong>{s.value}</strong>
              <span>{s.label}</span>
            </div>
          ))}
          <p>Bukit Jelutong prototype. Building shapes and roads are real; business data is simulated.</p>
        </div>
      </header>

      <main>
        <section className="lp-section lp-problem">
          <div>
            <p className="lp-kicker">The problem</p>
            <h2>Masterplans are static. Townships are not.</h2>
            <p className="lp-body">
              Plans are made years ahead, then people, shops and habits change. Assets the plan
              expected to thrive sit underused, and the usual answer is still to build something new.
            </p>
            <div className="lp-facts">
              <p><strong>37%</strong> of global emissions come from buildings and construction.</p>
              <p><strong>Nearly 50%</strong> of global material extraction goes to the same sector.</p>
            </div>
            <p className="lp-source">Source: UNEP & GlobalABC, 2025–2026</p>
          </div>
          <div className="lp-ledger">
            <h3>What deadspace costs</h3>
            {DEADSPACE_COSTS.map((c) => (
              <div key={c.name}>
                <h4>{c.name}</h4>
                <p>{c.text}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="lp-section" id="how">
          <p className="lp-kicker">How it works</p>
          <h2>Five steps from a flagged building to a decision</h2>
          <p className="lp-body">Followed here through one saved prototype run on a real building footprint, using simulated business data.</p>
          <ol className="lp-steps">
            <li className="lp-steps-head" aria-hidden="true">
              <span>Step</span><span>What the system does</span><span>Example: BLD-0037</span>
            </li>
            {STEPS.map((s, i) => (
              <li key={s.name}>
                <h3><span>{i + 1}</span>{s.name}</h3>
                <p>{s.what}</p>
                <p className="lp-example">{s.example}</p>
              </li>
            ))}
          </ol>
        </section>

        <section className="lp-section lp-tinted" id="concepts">
          <div className="lp-inner">
            <p className="lp-kicker">Key concepts</p>
            <h2>The ideas behind it, in plain words</h2>
            <dl className="lp-concepts">
              {CONCEPTS.map((c) => (
                <div key={c.term}>
                  <dt>{c.term}</dt>
                  <dd>{c.text}</dd>
                </div>
              ))}
            </dl>
          </div>
        </section>

        <section className="lp-trust" id="trust">
          <div className="lp-inner">
            <p className="lp-kicker">Why you can check it</p>
            <h2>Tools calculate the world. AI reasons about it.</h2>
            <div className="lp-trust-grid">
              <div>
                <h3>Every number shows where it came from</h3>
                <ul className="lp-tiers">
                  {TIERS.map((t) => (
                    <li key={t.name}><i className={t.tier} /><b>{t.name}</b><span>{t.text}</span></li>
                  ))}
                </ul>
              </div>
              <div>
                <h3>The AI has limits</h3>
                <ul className="lp-rules">
                  {RULES.map((r) => <li key={r}>{r}</li>)}
                </ul>
              </div>
            </div>
          </div>
        </section>

        <section className="lp-section">
          <p className="lp-kicker">Impact</p>
          <h2>One decision, three kinds of value</h2>
          <div className="lp-impact">
            {IMPACT.map((v) => (
              <article key={v.who}>
                <h3>{v.who}</h3>
                <p>{v.text}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="lp-section lp-see">
          <div>
            <p className="lp-kicker">See it working</p>
            <h2>Start with the township. End with a plan.</h2>
            <p className="lp-body">
              Explore the 3D map, open the flagged list, select an asset and ask a question.
              A full AI analysis can take a couple of minutes because every plan is simulated.
            </p>
            <a className="lp-cta" href={DEMO_HREF}>Launch demo</a>
          </div>
          <img src="/landing/app-screenshot.jpg" width="1600" height="900" alt="Living Masterplan app showing a 3D map of Bukit Jelutong beside a list of flagged assets." />
        </section>

        <section className="lp-section lp-tinted" id="references">
          <div className="lp-inner">
            <p className="lp-kicker">References</p>
            <h2>Sources and methods</h2>
            <ol className="lp-refs">
              {REFERENCES.map((r) => (
                <li key={r.cite}>
                  {r.href ? <a href={r.href} target="_blank" rel="noreferrer">{r.cite}</a> : <span>{r.cite}</span>}
                  <small>{r.use}</small>
                </li>
              ))}
            </ol>
            <p className="lp-note">
              <b>About the data:</b> occupancy, leases and finances in this prototype are simulated for
              Bukit Jelutong. A pilot would connect the township’s own database through the same format.
            </p>
          </div>
        </section>
      </main>

      <footer className="lp-footer">
        <div>
          <h2>Ask before adding carbon.</h2>
          <a className="lp-cta" href={DEMO_HREF}>Launch demo</a>
        </div>
        <p>Built by {TEAM.join(', ')} for the Township of Tomorrow Hackathon 2026.</p>
      </footer>
    </div>
  )
}
