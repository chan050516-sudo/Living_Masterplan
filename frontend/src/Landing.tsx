import { useEffect, useRef, useState } from 'react'
import type { CSSProperties } from 'react'
import type { Scene3D } from './township3d'
import { fetchProfiles } from './api'
import { Evidence } from './Evidence'
import './landing.css'

const DEMO_HREF = '#/demo'

// Shown until GET /api/assets/profiles answers, and kept if it fails.
const HEADLINE = [
  { value: '916', label: 'assets analysed' },
  { value: '81', label: 'deadspace candidates' },
  { value: '31,011', label: 'tCO₂e a year stranded' },
  { value: '5 years', label: 'simulated for every plan' },
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

const BRING_YOUR_OWN = [
  { name: 'Connect your data', text: 'Add the township’s buildings, leases and occupancy in the standard format.' },
  { name: 'Run the analysis', text: 'The same rules and models find what needs attention.' },
  { name: 'Compare the plans', text: 'Test reuse, improve and build options before committing capital.' },
]

const IMPACT = [
  { who: 'Planet', text: 'Keeps embodied carbon in existing structures, reduces material extraction and finds carbon wasted on unused space.' },
  { who: 'SDP', text: 'Compares reuse, improve and build options before capital is committed, with the reasoning written down.' },
  { who: 'Residents', text: 'Turns idle space into what the neighbourhood needs, closer to home and easier to reach on foot.' },
]

// Plays once per page load, so coming back from the demo does not repeat it.
let introPlayed = false
const INTRO_MS = 3000
const INTRO_BLOCKS = [46, 92, 34, 70, 128, 58, 30, 84, 52]

function Intro() {
  const [phase, setPhase] = useState<'play' | 'open' | 'done'>(() => (
    introPlayed || window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'done' : 'play'
  ))
  const playing = useRef(false)
  useEffect(() => {
    if (introPlayed && !playing.current) return
    playing.current = true
    introPlayed = true
    const open = setTimeout(() => setPhase('open'), INTRO_MS - 800)
    const done = setTimeout(() => setPhase('done'), INTRO_MS)
    return () => { clearTimeout(open); clearTimeout(done) }
  }, [])
  if (phase === 'done') return null
  return (
    <div className={`lp-intro ${phase}`} aria-hidden="true" onClick={() => setPhase('done')}>
      <i className="lp-curtain top" />
      <i className="lp-curtain bottom" />
      <div className="lp-intro-mark">
        <div className="lp-tile">
          {INTRO_BLOCKS.map((h, i) => (
            <div key={i} className={`lp-block${i === 4 ? ' dead' : ''}`} style={{ '--h': `${h}px`, '--d': `${i * 90}ms` } as CSSProperties}>
              <b className="t" /><b className="n" /><b className="e" /><b className="s" /><b className="w" />
            </div>
          ))}
        </div>
        <p>LIVING MASTERPLAN</p>
      </div>
    </div>
  )
}

const fmt = (n: number) => Math.round(n).toLocaleString('en-US')

/** The headline counts, refreshed from the live API. */
function useHeadline() {
  const [stats, setStats] = useState(HEADLINE)
  useEffect(() => {
    let live = true
    fetchProfiles().then((profiles) => {
      const all = Object.values(profiles)
      if (!live || all.length === 0) return
      const dead = all.filter((p) => p.deadspace_diagnosis?.status === 'deadspace_candidate').length
      const stranded = all.reduce((sum, p) => sum + (p.environmental?.carbon_stranded_tco2e ?? 0), 0)
      setStats([
        { ...HEADLINE[0], value: fmt(all.length) },
        { ...HEADLINE[1], value: fmt(dead) },
        { ...HEADLINE[2], value: fmt(stranded) },
        HEADLINE[3],
      ])
    }).catch(() => { /* keep the saved snapshot */ })
    return () => { live = false }
  }, [])
  return stats
}

function CountUp({ value }: { value: string }) {
  const [shown, setShown] = useState(value)
  const ref = useRef<HTMLElement>(null)
  useEffect(() => {
    const match = value.match(/[\d,]+/)
    const el = ref.current
    if (!match || !el || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    const end = Number(match[0].replace(/,/g, ''))
    let raf = 0
    const io = new IntersectionObserver(([e]) => {
      if (!e.isIntersecting) return
      io.disconnect()
      const start = performance.now()
      const tick = (t: number) => {
        const p = Math.min((t - start) / 1600, 1)
        const n = Math.round(end * (1 - Math.pow(1 - p, 3)))
        setShown(value.replace(match[0], n.toLocaleString('en-US')))
        if (p < 1) raf = requestAnimationFrame(tick)
      }
      raf = requestAnimationFrame(tick)
    })
    io.observe(el)
    return () => { io.disconnect(); cancelAnimationFrame(raf) }
  }, [value])
  return <strong ref={ref}>{shown}</strong>
}

function useScene() {
  const canvas = useRef<HTMLCanvasElement>(null)
  const scene = useRef<Scene3D | null>(null)
  const [ready, setReady] = useState(false)
  useEffect(() => {
    let cancelled = false
    const el = canvas.current
    if (!el || !document.createElement('canvas').getContext('webgl2')) return
    const still = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const light = window.innerWidth < 960
    // Loaded on demand. If it fails, the flat map stays on screen.
    // Start behind the opening animation so the buildings rise as it opens.
    new Promise((done) => setTimeout(done, Math.max(300, INTRO_MS - 900 - performance.now())))
      .then(() => import('./township3d'))
      .then(({ startTownship }) => startTownship(el, { still, light }))
      .then((s) => {
        if (cancelled) { s.dispose(); return }
        scene.current = s
        setReady(true)
      })
      .catch(() => {})
    return () => { cancelled = true; scene.current?.dispose(); scene.current = null }
  }, [])
  return { canvas, scene, ready }
}

export function Landing() {
  const { canvas, scene, ready } = useScene()
  const root = useRef<HTMLDivElement>(null)
  const [step, setStep] = useState(-1)
  const headline = useHeadline()

  useEffect(() => { scene.current?.setStep(step) }, [step, ready, scene])

  useEffect(() => {
    const el = root.current
    if (!el) return
    const onScroll = () => scene.current?.setScroll(Math.min(window.scrollY / window.innerHeight, 1))
    window.addEventListener('scroll', onScroll, { passive: true })

    const reveal = new IntersectionObserver((list) => {
      list.forEach((e) => { if (e.isIntersecting) { e.target.classList.add('in'); reveal.unobserve(e.target) } })
    }, { rootMargin: '0px 0px -8% 0px' })
    el.querySelectorAll('.rv').forEach((n) => reveal.observe(n))

    const beats = new IntersectionObserver((list) => {
      list.forEach((e) => { if (e.isIntersecting) setStep(Number((e.target as HTMLElement).dataset.step)) })
    }, { rootMargin: '-50% 0px -50% 0px' })
    el.querySelectorAll('[data-step]').forEach((n) => beats.observe(n))

    // Stop drawing while solid sections fully cover the canvas.
    const seen = new Set<Element>()
    const stage = new IntersectionObserver((list) => {
      list.forEach((e) => { if (e.isIntersecting) seen.add(e.target); else seen.delete(e.target) })
      scene.current?.setActive(seen.size > 0)
    })
    el.querySelectorAll('.lp-open').forEach((n) => stage.observe(n))

    return () => { window.removeEventListener('scroll', onScroll); reveal.disconnect(); beats.disconnect(); stage.disconnect() }
  }, [scene])

  return (
    <div className={`lp${ready ? ' lp-3d' : ''}`} ref={root}>
      <Intro />
      <canvas className="lp-canvas" ref={canvas} aria-hidden="true" />
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

      <header className="lp-hero lp-open" id="top" data-step="-1">
        <div className="lp-hero-text">
          <h1 className="rise">Don’t just build greener. <em>Build only what the future still needs.</em></h1>
          <p className="lp-lede rise">
            Works for any township. Connect your own data, find the assets that have stopped giving
            value back, then test whether to reuse, improve or build, five years ahead.
          </p>
          <div className="lp-hero-actions rise">
            <a className="lp-cta" href={DEMO_HREF}>Launch demo</a>
            <a className="lp-quiet" href="#how">See how it works</a>
          </div>
        </div>
        <figure className="lp-hero-map">
          <img src="/landing/township-map.svg" width="1020" height="1010" alt="Building footprints of the example township, Bukit Jelutong, with deadspace candidates highlighted in orange and assets to watch in pale grey." />
        </figure>
        <p className="lp-legend">
          <span><i className="ok" />Healthy</span>
          <span><i className="watch" />Watch</span>
          <span><i className="dead" />Deadspace candidate</span>
          <span><i className="smoke" />Stranded carbon</span>
        </p>
        <div className="lp-stats">
          {headline.map((s) => (
            <div key={s.label}>
              <CountUp key={s.value} value={s.value} />
              <span>{s.label}</span>
            </div>
          ))}
          <p>Example township: Bukit Jelutong. Building shapes and roads are real; business data is simulated.</p>
        </div>
      </header>

      <main>
        <section className="lp-story lp-open" id="how">
          <div className="lp-story-head" data-step="0">
            <p className="lp-kicker">How it works</p>
            <h2>Five steps from a flagged building to a decision</h2>
            <p className="lp-body">One saved prototype run on a real building footprint, using simulated business data. Keep scrolling.</p>
          </div>
          <ol className="lp-steps">
            {STEPS.map((s, i) => (
              <li key={s.name} data-step={i} className={step === i ? 'on' : ''}>
                <h3><span>{i + 1}</span>{s.name}</h3>
                <p>{s.what}</p>
                <p className="lp-example"><b>BLD-0037</b>{s.example}</p>
              </li>
            ))}
          </ol>
        </section>

        <div className="lp-sheet">
        <section className="lp-section lp-tinted" id="concepts">
          <div className="lp-inner">
            <p className="lp-kicker">Key concepts</p>
            <h2>The ideas behind it, in plain words</h2>
            <dl className="lp-concepts rv">
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
            <div className="lp-trust-grid rv">
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
          <p className="lp-kicker">Any township</p>
          <h2>Any township. Your data. Tested on Bukit Jelutong.</h2>
          <p className="lp-body">There is no fixed database. Each township or project connects its own data through one standard format, without rebuilding the system.</p>
          <ol className="lp-byo rv">
            {BRING_YOUR_OWN.map((b, i) => (
              <li key={b.name}>
                <span>{i + 1}</span>
                <h3>{b.name}</h3>
                <p>{b.text}</p>
              </li>
            ))}
          </ol>
        </section>

        <section className="lp-section">
          <p className="lp-kicker">Impact</p>
          <h2>One decision, three kinds of value</h2>
          <div className="lp-impact rv">
            {IMPACT.map((v) => (
              <article key={v.who}>
                <h3>{v.who}</h3>
                <p>{v.text}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="lp-section lp-see rv">
          <div>
            <p className="lp-kicker">See it working</p>
            <h2>Start with the township. End with a plan.</h2>
            <p className="lp-body">
              Explore the 3D map, open the flagged list, select an asset and ask a question.
              A full AI analysis can take a couple of minutes because every plan is simulated.
            </p>
            <a className="lp-cta" href={DEMO_HREF}>Launch demo</a>
          </div>
          <img src="/landing/app-screenshot.jpg" width="1600" height="900" alt="Living Masterplan app showing a 3D map of the example township, Bukit Jelutong, beside a list of flagged assets." />
        </section>

        <Evidence />
        </div>
      </main>

      <footer className="lp-footer">
        <a className="lp-brand" href="#top">LIVING MASTERPLAN</a>
        <img src="/landing/sdp-logo.png" alt="Sime Darby Property" onError={(e) => { e.currentTarget.style.display = 'none' }} />
        <p>© 2026 Living Masterplan</p>
      </footer>

    </div>
  )
}
