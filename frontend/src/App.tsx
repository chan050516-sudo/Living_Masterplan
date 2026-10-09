import { useEffect, useRef, useState } from 'react'
import * as maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'

maplibregl.setWorkerUrl(workerUrl)
type AiOption = {
  id: string
  title: string
  summary: string
  capex: string
  score_after: number
  changes: string[]
}

type AiAnswer = {
  analysis: string
  options: AiOption[]
}

type ComparisonRow = {
  label: string
  current: string
  a: string
  b: string
  c: string
}

type Comparison = {
  rows: ComparisonRow[]
  recommended: string
  reason: string
}

type Asset = {
  id: string
  name: string
  type: string
  score: number
  occupancy: number
  vacancy_months: number
  score_3y: number
  occupancy_3y: number
}

export default function App() {
  const mapContainer = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  const [selected, setSelected] = useState<Asset | null>(null)
  const [year, setYear] = useState<'now' | '3y'>('now')
  const [assets, setAssets] = useState<Asset[]>([])
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState<AiAnswer | null>(null)
  const [loading, setLoading] = useState(false)
  const [preview, setPreview] = useState<AiOption | null>(null)
  const [comparison, setComparison] = useState<Comparison | null>(null)

  async function simulate() {
    if (!selected) return
    const res = await fetch('/data/comparison.json')
    const all = await res.json()
    setComparison(all[selected.id] ?? null)
    console.log('simulate', { id: selected.id, found: !!all[selected.id] })
  }

  function showPreview(o: AiOption) {
    setPreview(o)
    const map = mapRef.current
    if (!map || !map.getLayer('assets-fill') || !selected) return
    map.setPaintProperty('assets-fill', 'fill-color', [
      'case',
      ['==', ['get', 'id'], selected.id], '#1e88e5',
      [
        'step', ['get', year === 'now' ? 'score' : 'score_3y'],
        '#e53935', 40,
        '#fdd835', 60,
        '#43a047',
      ],
    ])
  }

  function clearPreview() {
    setPreview(null)
    const map = mapRef.current
    if (!map || !map.getLayer('assets-fill')) return
    map.setPaintProperty('assets-fill', 'fill-color', [
      'step', ['get', year === 'now' ? 'score' : 'score_3y'],
      '#e53935', 40,
      '#fdd835', 60,
      '#43a047',
    ])
  }

  async function ask() {
    if (!selected) return
    setLoading(true)
    const res = await fetch('/data/options.json')
    const all = await res.json()
    setTimeout(() => {
      setAnswer(all[selected.id] ?? null)
      setLoading(false)
    }, 600)
  }

  useEffect(() => {
    fetch('/data/assets.geojson')
      .then((r) => r.json())
      .then((d) => setAssets(d.features.map((f: { properties: Asset }) => f.properties)))
  }, [])

  useEffect(() => {
    if (!mapContainer.current) return

    const map = new maplibregl.Map({
      container: mapContainer.current,
      style: {
        version: 8,
        sources: {
          osm: {
            type: 'raster',
            tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
            tileSize: 256,
            attribution: '© OpenStreetMap contributors',
          },
        },
        layers: [{ id: 'osm', type: 'raster', source: 'osm' }],
      },
      center: [101.5005, 3.1915],
      zoom: 15,
    })

    mapRef.current = map

    map.on('load', () => {
      map.addSource('assets', { type: 'geojson', data: '/data/assets.geojson' })

      map.addLayer({
        id: 'assets-fill',
        type: 'fill',
        source: 'assets',
        paint: {
          'fill-color': [
            'step', ['get', 'score'],
            '#e53935', 40,
            '#fdd835', 60,
            '#43a047',
          ],
          'fill-opacity': 0.7,
        },
      })

      map.addLayer({
        id: 'assets-outline',
        type: 'line',
        source: 'assets',
        paint: { 'line-color': '#222', 'line-width': 2 },
      })

      map.on('click', 'assets-fill', (e) => {
        const props = e.features?.[0]?.properties
        if (props) setSelected(props as Asset)
      })

      map.on('mouseenter', 'assets-fill', () => {
        map.getCanvas().style.cursor = 'pointer'
      })
      map.on('mouseleave', 'assets-fill', () => {
        map.getCanvas().style.cursor = ''
      })
    })

    return () => map.remove()
  }, [])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !map.getLayer('assets-fill')) return
    const field = year === 'now' ? 'score' : 'score_3y'
    map.setPaintProperty('assets-fill', 'fill-color', [
      'step', ['get', field],
      '#e53935', 40,
      '#fdd835', 60,
      '#43a047',
    ])
  }, [year])

  const score = selected ? (year === 'now' ? selected.score : selected.score_3y) : 0
  const occ = selected ? (year === 'now' ? selected.occupancy : selected.occupancy_3y) : 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', width: '100vw', height: '100vh', fontFamily: 'sans-serif' }}>
      <div style={{ padding: '10px 20px', borderBottom: '1px solid #ddd', display: 'flex', gap: 10, alignItems: 'center' }}>
        <strong>Living Masterplan</strong>
        <span style={{ marginLeft: 'auto' }} />
        <button onClick={() => setYear('now')} style={{ fontWeight: year === 'now' ? 700 : 400 }}>Current</button>
        <button onClick={() => setYear('3y')} style={{ fontWeight: year === '3y' ? 700 : 400 }}>+3 years</button>
      </div>
      <div style={{ display: 'flex', flex: 1 }}>
            {comparison && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', zIndex: 10, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <div style={{ background: '#fff', padding: 24, borderRadius: 8, maxWidth: 760, width: '90%', maxHeight: '85vh', overflowY: 'auto' }}>
            <h2 style={{ marginTop: 0 }}>Scenario comparison</h2>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
              <thead>
                <tr>
                  <th style={{ textAlign: 'left', padding: 8, borderBottom: '2px solid #333' }}>Metric</th>
                  <th style={{ textAlign: 'left', padding: 8, borderBottom: '2px solid #333' }}>Current</th>
                  <th style={{ textAlign: 'left', padding: 8, borderBottom: '2px solid #333' }}>Option A</th>
                  <th style={{ textAlign: 'left', padding: 8, borderBottom: '2px solid #333' }}>Option B</th>
                  <th style={{ textAlign: 'left', padding: 8, borderBottom: '2px solid #333' }}>Option C</th>
                </tr>
              </thead>
              <tbody>
                {comparison.rows.map((r) => (
                  <tr key={r.label}>
                    <td style={{ padding: 8, borderBottom: '1px solid #eee' }}>{r.label}</td>
                    <td style={{ padding: 8, borderBottom: '1px solid #eee' }}>{r.current}</td>
                    <td style={{ padding: 8, borderBottom: '1px solid #eee' }}>{r.a}</td>
                    <td style={{ padding: 8, borderBottom: '1px solid #eee' }}>{r.b}</td>
                    <td style={{ padding: 8, borderBottom: '1px solid #eee' }}>{r.c}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div style={{ marginTop: 16, padding: 12, background: '#e8f5e9', borderRadius: 6 }}>
              <strong>Recommended: {comparison.recommended}</strong>
              <div style={{ fontSize: 13, marginTop: 4 }}>{comparison.reason}</div>
            </div>
            <button onClick={() => setComparison(null)} style={{ marginTop: 16 }}>Close</button>
          </div>
        </div>
      )}
        <div ref={mapContainer} style={{ flex: 1 }} />
        <div style={{ width: 340, padding: 20, overflowY: 'auto', background: '#fff', borderLeft: '1px solid #ddd' }}>
          {selected ? (
            <>
              <h2 style={{ marginTop: 0 }}>{selected.name}</h2>
              <p style={{ fontSize: 32, margin: '8px 0' }}>{score}<span style={{ fontSize: 16, color: '#777' }}> / 100</span></p>
              <p style={{ color: '#777', fontSize: 13 }}>{year === 'now' ? 'Observed' : 'Scenario (+3 years)'}</p>
              <p>Type: {selected.type}</p>
              <p>Occupancy: {occ}%</p>
              <p>Vacant for: {selected.vacancy_months} months</p>
                            <hr style={{ margin: '16px 0', border: 0, borderTop: '1px solid #eee' }} />

              {!answer && (
                <>
                  <p style={{ fontSize: 13, color: '#777' }}>Ask a question about {selected.id}</p>
                  <input
                    value={question}
                    onChange={(e) => setQuestion(e.target.value)}
                    placeholder="What should we do with this asset?"
                    style={{ width: '100%', padding: 8, boxSizing: 'border-box', marginBottom: 8 }}
                  />
                  <button onClick={ask} disabled={loading}>{loading ? 'Thinking…' : 'Ask'}</button>
                </>
              )}

              {answer && (
                <>
                  <p style={{ fontSize: 13, color: '#777' }}>Your question</p>
                  <p style={{ fontStyle: 'italic' }}>{question || 'What should we do with this asset?'}</p>
                  <p>{answer.analysis}</p>
                  {answer.options.map((o) => (
                    <div key={o.id} style={{ padding: 12, marginBottom: 10, border: '1px solid #ddd', borderRadius: 6 }}>
                      <strong>{o.title}</strong>
                      <div style={{ fontSize: 13, margin: '4px 0' }}>{o.summary}</div>
                      <div style={{ fontSize: 13, color: '#777' }}>CAPEX {o.capex} · Score after {o.score_after}</div>
                      <button onClick={() => showPreview(o)} style={{ marginTop: 8 }}>Preview on map</button>
                      <button onClick={simulate} style={{ marginTop: 8, marginLeft: 6 }}>Simulate</button>
                    </div>
                  ))}
                </>
              )}

                            <button onClick={() => { setSelected(null); setAnswer(null); setQuestion(''); clearPreview() }} style={{ marginTop: 10 }}>Close</button>
              {preview && (
                <div style={{ marginTop: 10, padding: 12, background: '#e3f2fd', borderRadius: 6 }}>
                  <strong>Preview: {preview.title}</strong>
                  <ul style={{ paddingLeft: 18, margin: '8px 0' }}>
                    {preview.changes.map((c) => <li key={c} style={{ fontSize: 13 }}>{c}</li>)}
                  </ul>
                  <button onClick={clearPreview}>Clear preview</button>
                </div>
              )}
                            {preview && (
                <div style={{ marginTop: 10, padding: 12, background: '#e3f2fd', borderRadius: 6 }}>
                  <strong>Preview: {preview.title}</strong>
                  <ul style={{ paddingLeft: 18, margin: '8px 0' }}>
                    {preview.changes.map((c) => <li key={c} style={{ fontSize: 13 }}>{c}</li>)}
                  </ul>
                  <button onClick={clearPreview}>Clear preview</button>
                </div>
              )}
            </>
          ) : (
            <>
              <h3 style={{ marginTop: 0 }}>Deadspace candidates</h3>
              {assets
                .filter((a) => (year === 'now' ? a.score : a.score_3y) < 60)
                .sort((a, b) => (year === 'now' ? a.score - b.score : a.score_3y - b.score_3y))
                .map((a) => {
                  const s = year === 'now' ? a.score : a.score_3y
                  return (
                    <div
                      key={a.id}
                      onClick={() => setSelected(a)}
                      style={{ padding: 12, marginBottom: 10, border: '1px solid #ddd', borderRadius: 6, cursor: 'pointer' }}
                    >
                      <strong>{a.name}</strong>
                      <div style={{ color: s < 40 ? '#e53935' : '#f9a825' }}>Score: {s}</div>
                      {a.vacancy_months > 0 && (
                        <div style={{ color: '#777', fontSize: 13 }}>Vacant {a.vacancy_months} months</div>
                      )}
                    </div>
                  )
                })}
              <p style={{ color: '#777', fontSize: 13 }}>Or click any asset on the map.</p>
            </>
          )}
        </div>
      </div>
    </div>
  )
}