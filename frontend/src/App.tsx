import { useEffect, useMemo, useRef, useState } from 'react'
import * as maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'
import { C, statusColorExpr } from './theme'
import { MapLegend, MapControls } from './components/ui'
import { DeadspaceList } from './components/DeadspaceList'
import { AssetPanel } from './components/AssetPanel'
import { ComparisonModal } from './components/ComparisonModal'
import { analyze, getAssetProfiles, getMapGeometry } from './api'
import type { AnalyzeResult, AssetProfiles, MapGeometry } from './types'

maplibregl.setWorkerUrl(workerUrl)

const EMPTY: MapGeometry = { type: 'FeatureCollection', features: [] }
const CLICKABLE = ['assets-points', 'assets-3d', 'assets-lines'] as const

type Geom = MapGeometry['features'][number]['geometry']

// All [lng, lat] positions of a feature
function positionsOf(g: Geom): number[][] {
  switch (g.type) {
    case 'Point': return [g.coordinates]
    case 'MultiPoint': case 'LineString': return g.coordinates
    case 'MultiLineString': case 'Polygon': return g.coordinates.flat()
    case 'MultiPolygon': return g.coordinates.flat(2)
    case 'GeometryCollection': return g.geometries.flatMap(positionsOf)
  }
}

// Rough centre of a feature: average of its positions
function centerOf(g: Geom): [number, number] | null {
  const pts = positionsOf(g)
  if (!pts.length) return null
  const [x, y] = pts.reduce(([sx, sy], [px, py]) => [sx + px, sy + py], [0, 0])
  return [x / pts.length, y / pts.length]
}

function boundsOf(fc: MapGeometry): maplibregl.LngLatBounds | null {
  const b = new maplibregl.LngLatBounds()
  for (const f of fc.features) if (f.geometry) for (const [x, y] of positionsOf(f.geometry)) b.extend([x, y])
  return b.isEmpty() ? null : b
}

export default function App() {
  const mapContainer = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  const markerRef = useRef<maplibregl.Marker | null>(null)
  const fitted = useRef(false)

  const [mapReady, setMapReady] = useState(false)
  const [profiles, setProfiles] = useState<AssetProfiles>({})
  const [geometry, setGeometry] = useState<MapGeometry>(EMPTY)
  const [planGeometry, setPlanGeometry] = useState<MapGeometry | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [bearing, setBearing] = useState(-20)
  const [tilted, setTilted] = useState(true)
  const [question, setQuestion] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [result, setResult] = useState<AnalyzeResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showPlan, setShowPlan] = useState(false)
  const [showResults, setShowResults] = useState(false)

  const profileList = useMemo(() => Object.values(profiles), [profiles])
  const centers = useMemo(() => {
    const m = new Map<string, [number, number]>()
    for (const f of geometry.features) {
      const c = f.geometry && f.properties.asset_id ? centerOf(f.geometry) : null
      if (c && !m.has(f.properties.asset_id!)) m.set(f.properties.asset_id!, c)
    }
    return m
  }, [geometry])
  const selected = selectedId ? profiles[selectedId] : undefined

  // ---- 1. Load profiles + geometry once ----
  useEffect(() => {
    Promise.all([getAssetProfiles(), getMapGeometry()])
      .then(([p, g]) => { setProfiles(p); setGeometry(g) })
      .catch((e: Error) => setLoadError(e.message))
  }, [])

  // ---- 2. Create the map ----
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
      center: [101.53, 3.11],
      zoom: 14,
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
      map.addSource('assets', { type: 'geojson', data: EMPTY })
      map.addLayer({
        id: 'assets-3d',
        type: 'fill-extrusion',
        source: 'assets',
        filter: ['in', ['geometry-type'], ['literal', ['Polygon', 'MultiPolygon']]] as never,
        paint: {
          'fill-extrusion-color': statusColorExpr(),
          // Buildings carry height_m; parcels, green areas and amenity footprints stay low
          'fill-extrusion-height': ['coalesce', ['get', 'height_m'], 1] as never,
          'fill-extrusion-vertical-gradient': true,
          'fill-extrusion-opacity': 0.92,
        },
      })
      map.addLayer({
        id: 'assets-lines',
        type: 'line',
        source: 'assets',
        filter: ['in', ['geometry-type'], ['literal', ['LineString', 'MultiLineString']]] as never,
        paint: { 'line-color': statusColorExpr(), 'line-width': 2, 'line-opacity': 0.8 },
      })
      map.addLayer({
        id: 'assets-points',
        type: 'circle',
        source: 'assets',
        filter: ['==', ['geometry-type'], 'Point'],
        paint: {
          'circle-color': statusColorExpr(),
          'circle-radius': 6,
          'circle-stroke-color': '#1a1419',
          'circle-stroke-width': 1.5,
        },
      })

      for (const layer of CLICKABLE) {
        map.on('click', layer, (e) => {
          const id = e.features?.[0]?.properties?.asset_id as string | undefined
          if (id) pick(id)
        })
        map.on('mouseenter', layer, () => { map.getCanvas().style.cursor = 'pointer' })
        map.on('mouseleave', layer, () => { map.getCanvas().style.cursor = '' })
      }
      setMapReady(true)
    })

    return () => map.remove()
  }, [])

  // ---- 3. Push geometry (baseline or AI plan) into the map ----
  useEffect(() => {
    const map = mapRef.current
    if (!map || !mapReady) return
    const data = showPlan && planGeometry ? planGeometry : geometry
    ;(map.getSource('assets') as maplibregl.GeoJSONSource).setData(data)
    if (!fitted.current && data.features.length) {
      const b = boundsOf(data)
      if (b) map.fitBounds(b, { padding: 40, duration: 0 })
      fitted.current = true
    }
  }, [mapReady, geometry, planGeometry, showPlan])

  // ---- 4. Highlight the selected asset ----
  useEffect(() => {
    const map = mapRef.current
    if (!map || !mapReady) return
    const color = selectedId && !showPlan
      ? ['case', ['==', ['get', 'asset_id'], selectedId], C.selected, statusColorExpr()] as never
      : statusColorExpr()
    map.setPaintProperty('assets-3d', 'fill-extrusion-color', color)
    map.setPaintProperty('assets-lines', 'line-color', color)
    map.setPaintProperty('assets-points', 'circle-color', color)
  }, [mapReady, selectedId, showPlan])

  // ---- 5. Floating label over the selected asset ----
  useEffect(() => {
    const map = mapRef.current
    markerRef.current?.remove()
    markerRef.current = null
    const center = selectedId ? centers.get(selectedId) : undefined
    if (!map || !selected || !center) return

    // MapLibre positions the marker element with a CSS transform, so the
    // pop-in animation (which also animates transform) goes on an inner box.
    const el = document.createElement('div')
    el.style.pointerEvents = 'none'
    const box = document.createElement('div')
    box.style.cssText = 'display:flex;flex-direction:column;align-items:center;animation:popIn .3s cubic-bezier(.22,.8,.3,1) both'
    el.append(box)
    const label = document.createElement('div')
    label.textContent = selected.identity.asset_name
    label.style.cssText = `
      background:rgba(26,20,26,.92);border:1px solid ${C.selected};border-radius:9px;
      padding:8px 14px;color:#fff;font:600 11.5px/1 system-ui,sans-serif;
      letter-spacing:.11em;text-transform:uppercase;white-space:nowrap;
      box-shadow:0 0 18px rgba(33,150,243,.45),0 6px 16px rgba(0,0,0,.5);
      backdrop-filter:blur(4px)`
    box.append(label)
    box.insertAdjacentHTML('beforeend', `
      <div style="width:0;height:30px;border-left:1px dashed rgba(255,255,255,.55)"></div>
      <div style="width:9px;height:9px;border-radius:50%;background:#fff;
        box-shadow:0 0 0 4px rgba(33,150,243,.35)"></div>`)
    markerRef.current = new maplibregl.Marker({ element: el, anchor: 'bottom' })
      .setLngLat(center)
      .addTo(map)
    map.easeTo({ center, zoom: Math.max(map.getZoom(), 16.3), pitch: 58, duration: 1100 })

    return () => { markerRef.current?.remove(); markerRef.current = null }
  }, [selectedId, selected, centers])

  function pick(id: string) {
    setSelectedId(id)
    setResult(null); setError(null); setQuestion(''); setFiles([])
    setShowPlan(false); setPlanGeometry(null)
  }

  async function ask() {
    if (!selectedId || loading) return
    const q = question.trim() || 'What should we do with this asset?'
    setLoading(true); setError(null)
    try {
      const r = await analyze(q, [selectedId], files)
      setResult(r)
      setQuestion(''); setFiles([])
      setPlanGeometry(await getMapGeometry(r.run_id))
      setShowPlan(true)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  function closePanel() {
    setSelectedId(null); setResult(null); setError(null); setQuestion(''); setFiles([])
    setShowPlan(false); setPlanGeometry(null)
  }

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
        <span style={{ fontSize: 13, color: C.muted }}>Bukit Jelutong</span>
        {showPlan && result && (
          <span className="pop" style={{
            fontSize: 11, letterSpacing: '.1em', textTransform: 'uppercase', color: C.selected,
            border: `1px solid ${C.selected}`, borderRadius: 5, padding: '3px 9px',
          }}>AI plan · {result.decision.selected_candidate}</span>
        )}
        <span style={{ flex: 1 }} />
        <span style={{ fontSize: 12, color: C.faint }}>{profileList.length ? `${profileList.length} assets · 2026 baseline` : ''}</span>
      </header>

      {showResults && result && (
        <ComparisonModal data={result} profiles={profiles} onClose={() => setShowResults(false)} />
      )}

      <div style={{ display: 'flex', flex: 1, minHeight: 0 }}>
        <main style={{ position: 'relative', flex: 1 }}>
          <div ref={mapContainer} style={{ position: 'absolute', inset: 0 }} />
          <MapLegend plan={showPlan} />
          <MapControls bearing={bearing} tilted={tilted} onZoom={zoomBy} onCompass={resetNorth} onTilt={toggleTilt} />
        </main>

        <aside className="panel" style={{
          width: 420, flex: 'none', padding: 22, overflowY: 'auto',
          background: C.panel, borderLeft: `1px solid ${C.line}`,
        }}>
          {loadError ? (
            <div style={{ fontSize: 13, color: C.bad, lineHeight: 1.6 }}>
              Could not reach the backend: {loadError}
              <p style={{ color: C.muted }}>Start it with <code>uvicorn app.api.main:app --port 8000</code> from the <code>backend</code> folder.</p>
            </div>
          ) : selected ? (
            <AssetPanel
              profile={selected}
              question={question} setQuestion={setQuestion}
              files={files} setFiles={setFiles}
              result={result} loading={loading} error={error} onAsk={ask}
              showPlan={showPlan} onTogglePlan={() => setShowPlan((v) => !v)}
              onShowResults={() => setShowResults(true)}
              onClose={closePanel}
            />
          ) : profileList.length ? (
            <DeadspaceList profiles={profileList} onPick={pick} />
          ) : (
            <p style={{ color: C.faint, fontSize: 13 }}>Loading township data…</p>
          )}
        </aside>
      </div>
    </div>
  )
}
