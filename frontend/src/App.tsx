import { useEffect, useRef } from 'react'
import * as maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'

maplibregl.setWorkerUrl(workerUrl)

export default function App() {
  const mapContainer = useRef<HTMLDivElement>(null)

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
    })

    return () => map.remove()
  }, [])

  return <div ref={mapContainer} style={{ width: '100vw', height: '100vh' }} />
}