import { useEffect, useRef, useState } from 'react'
import * as maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'
import { C, cap, btn, scoreColor } from './theme'
import { MapLegend, MapControls } from './components/ui'
import { DeadspaceList } from './components/DeadspaceList'
import { AssetPanel } from './components/AssetPanel'
import { ComparisonModal } from './components/ComparisonModal'
import type { Asset, AiAnswer, AiOption, Comparison } from './types'

maplibregl.setWorkerUrl(workerUrl)

export default function App() {
  const mapContainer = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  const markerRef = useRef<maplibregl.Marker | null>(null)
  const assetsRef = useRef<Asset[]>([])

  const [assets, setAssets] = useState<Asset[]>([])
  const [selected, setSelected] = useState<Asset | null>(null)
  const [year, setYear] = useState<'now' | '3y'>('now')
  const [bearing, setBearing] = useState(-20)
  const [tilted, setTilted] = useState(true)
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState<AiAnswer | null>(null)
  const [loading, setLoading] = useState(false)
  const [preview, setPreview] = useState<AiOption | null>(null)
  const [comparison, setComparison] = useState<Comparison | null>(null)

  async function ask() {
    if (!selected) return
    const asked = question.trim() || 'What should we do with this asset?'
    setLoading(true)
    const all = await (await fetch('/data/options.json')).json()
    setTimeout(() => {
      const found = all[selected.id]
      setAnswer(found ? { ...found, asked } : null)
      setQuestion('')
      setLoading(false)
    }, 600)
  }

  async function simulate() {
    if (!selected) return
    const all = await (await fetch('/data/comparison.json')).json()
    setComparison(all[selected.id] ?? null)
  }

  function closePanel() {
    setSelected(null); setAnswer(null); setQuestion(''); setPreview(null)
  }

  useEffect(() => {
    fetch('/data/assets.geojson')
      .then((r) => r.json())
      .then((d) => {
        const list = d.features.map((f: { properties: Asset }) => f.properties)
        assetsRef.current = list
        setAssets(list)
      })
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
            tiles: ['https://tiles.stadiamaps.com/tiles/alidade_smooth_dark/{z}/{x}/{y}.png'],
            tileSize: 256,
            attribution: '© OpenStreetMap contributors © Stadia Maps',
          },
        },
        layers: [{ id: 'osm', type: 'raster', source: 'osm' }],
      },
      center: [101.5005, 3.1915],
      zoom: 15,
      pitch: 55,
      bearing: -20,
      maxPitch: 80,
      dragRotate: true,
      pitchWithRotate: true,
      touchZoomRotate: true,
    })

    mapRef.current = map
    map.dragRotate.enable()
    map.touchZoomRotate.enableRotation()
    map.keyboard.enable()

    const sync = () => { setBearing(map.getBearing()); setTilted(map.getPitch() > 10) }
    map.on('rotate', sync)
    map.on('pitch', sync)

    map.on('load', () => {
      map.setSky({ 'sky-color': '#1a1320', 'horizon-color': '#4a3a48', 'sky-horizon-blend': 0.6 })
      map.addSource('assets', { type: 'geojson', data: '/data/assets.geojson' })
      map.addLayer({
        id: 'assets-3d',
        type: 'fill-extrusion',
        source: 'assets',
        paint: {
          'fill-extrusion-color': scoreColor('score') as never,
          'fill-extrusion-height': ['coalesce', ['get', 'height'], 30] as never,
          'fill-extrusion-vertical-gradient': true,
          'fill-extrusion-opacity': 0.92,
        },
      })

      map.on('click', 'assets-3d', (e) => {
        const id = e.features?.[0]?.properties?.id
        const found = assetsRef.current.find((a) => a.id === id)
        if (found) { setSelected(found); setAnswer(null); setQuestion(''); setPreview(null) }
        map.easeTo({ center: e.lngLat, zoom: 16.3, pitch: 58, duration: 1100 })
      })
      map.on('mouseenter', 'assets-3d', () => { map.getCanvas().style.cursor = 'pointer' })
      map.on('mouseleave', 'assets-3d', () => { map.getCanvas().style.cursor = '' })
    })

    return () => map.remove()
  }, [])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !map.getLayer('assets-3d')) return
    const f = year === 'now' ? 'score' : 'score_3y'

    if (preview && selected) {
      map.setPaintProperty('assets-3d', 'fill-extrusion-color', [
        'case',
        ['==', ['get', 'id'], selected.id], C.intervene,
        ['in', ['get', 'id'], ['literal', preview.spillover ?? []]], C.spill,
        scoreColor(f),
      ] as never)
    } else if (selected) {
      map.setPaintProperty('assets-3d', 'fill-extrusion-color', [
        'case',
        ['==', ['get', 'id'], selected.id], C.selected,
        scoreColor(f),
      ] as never)
    } else {
      map.setPaintProperty('assets-3d', 'fill-extrusion-color', scoreColor(f) as never)
    }
  }, [selected, preview, year])

  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    markerRef.current?.remove()
    markerRef.current = null
    if (!selected?.center) return

    const el = document.createElement('div')
    el.style.cssText = 'display:flex;flex-direction:column;align-items:center;pointer-events:none;animation:popIn .3s cubic-bezier(.22,.8,.3,1) both'
    el.innerHTML = `
      <div style="
        background:rgba(26,20,26,.92);border:1px solid ${C.selected};border-radius:9px;
        padding:8px 14px;color:#fff;font:600 11.5px/1 system-ui,sans-serif;
        letter-spacing:.11em;text-transform:uppercase;white-space:nowrap;
        box-shadow:0 0 18px rgba(33,150,243,.45),0 6px 16px rgba(0,0,0,.5);
        backdrop-filter:blur(4px)">${selected.name}</div>
      <div style="width:0;height:30px;border-left:1px dashed rgba(255,255,255,.55)"></div>
      <div style="width:9px;height:9px;border-radius:50%;background:#fff;
        box-shadow:0 0 0 4px rgba(33,150,243,.35)"></div>
    `
    markerRef.current = new maplibregl.Marker({ element: el, anchor: 'bottom' })
      .setLngLat(selected.center)
      .addTo(map)

    return () => { markerRef.current?.remove(); markerRef.current = null }
  }, [selected])

  const zoomBy = (d: 1 | -1) =>
    mapRef.current?.easeTo({ zoom: (mapRef.current.getZoom() ?? 15) + d, duration: 320 })

  const resetNorth = () =>
    mapRef.current?.easeTo({ bearing: 0, pitch: 55, duration: 600 })

  const toggleTilt = () => {
    const map = mapRef.current
    if (!map) return
    const flat = map.getPitch() < 10
    map.easeTo({ pitch: flat ? 58 : 0, bearing: flat ? -20 : 0, duration: 650 })
  }

  return (
    <div style={{
      display: 'flex', flexDirection: 'column', width: '100vw', height: '100vh',
      background: C.bg, color: C.text, fontFamily: 'system-ui, sans-serif',
    }}>
      <header style={{
        height: 58, flex: 'none', padding: '0 22px',
        borderBottom: `1px solid ${C.line}`, display: 'flex', alignItems: 'center',
        gap: 14, background: '#241c23',
      }}>
        <strong style={{ fontSize: 14, letterSpacing: '.14em' }}>LIVING MASTERPLAN</strong>
        <span style={{ fontSize: 13, color: C.muted }}>Elmina West</span>
        {preview && (
          <span className="pop" style={{
            fontSize: 11, letterSpacing: '.1em', textTransform: 'uppercase', color: C.selected,
            border: `1px solid ${C.selected}`, borderRadius: 5, padding: '3px 9px',
          }}>Preview · {preview.title}</span>
        )}
        <span style={{ flex: 1 }} />
        <span style={{ ...cap, marginRight: 4 }}>Horizon</span>
        <button className={`btn${year === 'now' ? ' primary' : ''}`} onClick={() => setYear('now')} style={btn(year === 'now')}>Current</button>
        <button className={`btn${year === '3y' ? ' primary' : ''}`} onClick={() => setYear('3y')} style={btn(year === '3y')}>+3 years</button>
      </header>

      {comparison && <ComparisonModal data={comparison} onClose={() => setComparison(null)} />}

      <div style={{ display: 'flex', flex: 1, minHeight: 0 }}>
        <main style={{ position: 'relative', flex: 1 }}>
          <div ref={mapContainer} style={{ position: 'absolute', inset: 0 }} />
          <MapLegend preview={!!preview} year={year} />
          <MapControls bearing={bearing} tilted={tilted} onZoom={zoomBy} onCompass={resetNorth} onTilt={toggleTilt} />
        </main>

        <aside className="panel" style={{
          width: 420, flex: 'none', padding: 22, overflowY: 'auto',
          background: C.panel, borderLeft: `1px solid ${C.line}`,
        }}>
          {selected ? (
            <AssetPanel
              asset={selected} year={year}
              question={question} setQuestion={setQuestion}
              answer={answer} loading={loading} onAsk={ask}
              preview={preview} onPreview={setPreview} onClearPreview={() => setPreview(null)}
              onSimulate={simulate} onClose={closePanel}
            />
          ) : (
            <DeadspaceList assets={assets} year={year} onPick={(a) => setSelected(a)} />
          )}
        </aside>
      </div>
    </div>
  )
}