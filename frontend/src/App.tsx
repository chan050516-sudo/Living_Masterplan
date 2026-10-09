import { useEffect, useRef, useState } from 'react'
import * as maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'

maplibregl.setWorkerUrl(workerUrl)

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
              <button onClick={() => setSelected(null)}>Close</button>
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