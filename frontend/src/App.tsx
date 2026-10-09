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
}

export default function App() {
  const mapContainer = useRef<HTMLDivElement>(null)
  const [selected, setSelected] = useState<Asset | null>(null)

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

  return (
    <div style={{ display: 'flex', width: '100vw', height: '100vh' }}>
      <div ref={mapContainer} style={{ flex: 1 }} />
      <div style={{ width: 340, padding: 20, overflowY: 'auto', background: '#fff', borderLeft: '1px solid #ddd', fontFamily: 'sans-serif' }}>
        {selected ? (
          <>
            <h2 style={{ marginTop: 0 }}>{selected.name}</h2>
            <p style={{ fontSize: 32, margin: '8px 0' }}>{selected.score}<span style={{ fontSize: 16, color: '#777' }}> / 100</span></p>
            <p>Type: {selected.type}</p>
            <p>Occupancy: {selected.occupancy}%</p>
            <p>Vacant for: {selected.vacancy_months} months</p>
            <button onClick={() => setSelected(null)}>Close</button>
          </>
        ) : (
          <p style={{ color: '#777' }}>Click an asset on the map.</p>
        )}
      </div>
    </div>
  )
}