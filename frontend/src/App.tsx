import { useEffect, useRef, useState } from 'react'
import * as maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'
import { C, cap, btn } from './theme'
import { MapLegend, MapControls } from './components/ui'
import { DeadspaceList } from './components/DeadspaceList'
import { AssetPanel } from './components/AssetPanel'
import { ComparisonModal } from './components/ComparisonModal'
import { fetchProfiles, fetchGeometry, runAnalysis } from './api'
import type { Asset, AssetProfile, AnalyzeResult } from './types'
import type { Feature, FeatureCollection, Geometry } from 'geojson'

maplibregl.setWorkerUrl(workerUrl)

const YEARS = [2026, 2027, 2028, 2030, 2033]
const METRES_PER_FLOOR = 3.2
const EMPTY: FeatureCollection = { type: 'FeatureCollection', features: [] }

/** Average of a polygon's outer ring, or the point itself. */
function centroidOf(geometry: Geometry): [number, number] {
  if (geometry.type === 'Point') {
    return [geometry.coordinates[0], geometry.coordinates[1]]
  }
  const ring =
    geometry.type === 'Polygon'
      ? geometry.coordinates[0]
      : geometry.type === 'MultiPolygon'
        ? geometry.coordinates[0][0]
        : null
  if (!ring || ring.length === 0) return [0, 0]
  let x = 0
  let y = 0
  for (const p of ring) { x += p[0]; y += p[1] }
  return [x / ring.length, y / ring.length]
}

/**
 * The API gives floor area and land area but not floor count, so infer it.
 * 13,475 m² of floor on 6,738 m² of land ≈ 2 storeys.
 */
function heightOf(profile: AssetProfile | null): number {
  const floor = profile?.physical.floor_area_m2
  const land = profile?.physical.land_area_m2
  if (!floor || !land || land <= 0) return 0
  const floors = Math.max(1, Math.round(floor / land))
  return Math.min(floors, 40) * METRES_PER_FLOOR
}

/** Status → colour. v1.2 §8.2 plus the API's own extra statuses. */
const STATUS_PAINT: maplibregl.ExpressionSpecification = [
  'match',
  ['get', 'status'],
  'healthy', '#3fb27f',
  'monitor', '#f7931d',
  'improvement_opportunity', '#f7931d',
  'development_risk', '#f15c22',
  'deadspace_candidate', '#d71920',
  'underperforming_facility', '#d71920',
  'intervened', '#2196f3',
  'vacant', '#9e9e9e',
  '#5a4f59',
]

const ASSET_LAYERS = ['assets-3d', 'area-fill', 'points-dot']

export default function App() {
  const mapContainer = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  const markersRef = useRef<maplibregl.Marker[]>([])
  const assetsRef = useRef<Asset[]>([])

  const buildingsRef = useRef<FeatureCollection>(EMPTY)
  const areaRef = useRef<FeatureCollection>(EMPTY)
  const pointsRef = useRef<FeatureCollection>(EMPTY)

  const [assets, setAssets] = useState<Asset[]>([])
  const [profilesData, setProfilesData] = useState<Record<string, AssetProfile>>({})
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [year, setYear] = useState(2026)
  const [bearing, setBearing] = useState(-20)
  const [tilted, setTilted] = useState(true)
  const [question, setQuestion] = useState('')
  const [analysis, setAnalysis] = useState<AnalyzeResult | null>(null)
  const [asked, setAsked] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [previewing, setPreviewing] = useState(false)
  const [showComparison, setShowComparison] = useState(false)
  const [mapReady, setMapReady] = useState(false)

  const selectedAssets = selectedIds
    .map((id) => assets.find((a) => a.id === id))
    .filter((a): a is Asset => !!a)

  const primary = selectedAssets[0] ?? null

  function reset() {
    setAnalysis(null); setAsked(''); setError(null)
    setPreviewing(false); setShowComparison(false)
  }

  function selectOnly(id: string) {
    setSelectedIds([id])
    setQuestion(''); reset()
    const a = assetsRef.current.find((x) => x.id === id)
    if (a) mapRef.current?.easeTo({ center: a.center, zoom: 17.5, pitch: 58, duration: 900 })
  }

  function toggleSelect(id: string) {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    )
    reset()
  }

  function closePanel() {
    setSelectedIds([]); setQuestion(''); reset()
  }

  /** Sends the question and the selected IDs to the B7 pipeline. */
  async function ask() {
    if (selectedAssets.length === 0) return
    const q = question.trim() || 'What should we do with these assets?'
    setLoading(true); setError(null); setAsked(q)
    try {
      const res = await runAnalysis(q, selectedIds)
      setAnalysis(res)
      setQuestion('')
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  function simulate() {
    if (analysis) setShowComparison(true)
  }

  // 1. Fetch Profiles once on mount (Base Year 2026 data)
  useEffect(() => {
    fetchProfiles()
      .then((profiles) => setProfilesData(profiles))
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
  }, [])

  // 2. Fetch Geometry and merge with profiles whenever `year` changes
  useEffect(() => {
    if (Object.keys(profilesData).length === 0) return

    fetchGeometry(undefined, year)
      .then((geo) => {
        const list: Asset[] = []
        const buildingFeatures: Feature[] = []
        const areaFeatures: Feature[] = []
        const pointFeatures: Feature[] = []

        for (const f of geo.features) {
          const p = (f.properties ?? {}) as Record<string, unknown>
          const id = String(p.asset_id ?? '')
          if (!id) continue
          if (f.geometry.type === 'LineString' || f.geometry.type === 'MultiLineString') continue

          const profile = profilesData[id] ?? null
          const mapStatus = String(p.map_status ?? 'healthy')
          const height = heightOf(profile)

          // Reconstruct a dynamic diagnosis object using backend geometry metadata
          // so the DeadspaceList (sidebar) updates its flags and urgency dynamically.
          const backendFlags = (p.flags as string[]) || []
          const backendUrgency = Number(p.urgency_index ?? 0)
          
          let dynamicDiagnosis = profile?.deadspace_diagnosis ?? null
          if (dynamicDiagnosis) {
            dynamicDiagnosis = {
              ...dynamicDiagnosis,
              status: mapStatus as any,
              flags: backendFlags,
              urgency_index: backendUrgency,
            }
          }

          list.push({
            id,
            name: profile?.identity.asset_name ?? id,
            subtype: profile?.identity.subtype ?? null,
            assetType: profile?.identity.asset_type ?? 'unknown',
            mapStatus,
            profile,
            diagnosis: dynamicDiagnosis,
            center: centroidOf(f.geometry),
            height,
          })

          const backendHeight = Number(p.height)
          const finalHeight = !Number.isNaN(backendHeight) && backendHeight > 0 
            ? backendHeight 
            : height

          const tagged: Feature = {
            ...f,
            properties: {
              ...f.properties,
              id,
              status: mapStatus,
              height: finalHeight,
            },
          }

          if (f.geometry.type === 'Point') pointFeatures.push(tagged)
          else if (height > 0) buildingFeatures.push(tagged)
          else areaFeatures.push(tagged)
        }

        buildingsRef.current = { type: 'FeatureCollection', features: buildingFeatures }
        areaRef.current = { type: 'FeatureCollection', features: areaFeatures }
        pointsRef.current = { type: 'FeatureCollection', features: pointFeatures }

        assetsRef.current = list
        setAssets(list)
        
        // Trigger map source update
        const map = mapRef.current
        if (map && mapReady) {
          ;(map.getSource('assets') as maplibregl.GeoJSONSource | undefined)?.setData(buildingsRef.current)
          ;(map.getSource('area') as maplibregl.GeoJSONSource | undefined)?.setData(areaRef.current)
          ;(map.getSource('points') as maplibregl.GeoJSONSource | undefined)?.setData(pointsRef.current)
        }
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
  }, [year, profilesData, mapReady])

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
      center: [101.528, 3.112],
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
      map.addSource('area', { type: 'geojson', data: EMPTY })
      map.addSource('points', { type: 'geojson', data: EMPTY })

      map.addLayer({
        id: 'area-fill',
        type: 'fill',
        source: 'area',
        paint: {
          'fill-color': STATUS_PAINT as never,
          'fill-opacity': 0.35,
        },
      })

      map.addLayer({
        id: 'assets-3d',
        type: 'fill-extrusion',
        source: 'assets',
        paint: {
          'fill-extrusion-color': STATUS_PAINT as never,
          'fill-extrusion-height': ['coalesce', ['get', 'height'], 8] as never,
          'fill-extrusion-vertical-gradient': true,
          'fill-extrusion-opacity': 0.92,
        },
      })

      map.addLayer({
        id: 'points-dot',
        type: 'circle',
        source: 'points',
        paint: {
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 13, 4, 18, 11] as never,
          'circle-color': STATUS_PAINT as never,
          'circle-stroke-width': 1.5,
          'circle-stroke-color': 'rgba(0,0,0,.55)',
        },
      })

      const onClick = (e: maplibregl.MapLayerMouseEvent) => {
        const id = e.features?.[0]?.properties?.id
        if (typeof id !== 'string') return
        const ev = e.originalEvent
        if (ev.ctrlKey || ev.metaKey || ev.shiftKey) toggleSelect(id)
        else selectOnly(id)
      }

      for (const layer of ASSET_LAYERS) {
        map.on('click', layer, onClick)
        map.on('mouseenter', layer, () => { map.getCanvas().style.cursor = 'pointer' })
        map.on('mouseleave', layer, () => { map.getCanvas().style.cursor = '' })
      }

      setMapReady(true)
    })

    return () => map.remove()
  }, [])

  // Fit the camera to the data once.
  const fittedRef = useRef(false)
  useEffect(() => {
    const map = mapRef.current
    if (!map || fittedRef.current || assets.length === 0) return
    const bounds = new maplibregl.LngLatBounds()
    for (const a of assets) {
      const [lng, lat] = a.center
      if (!Number.isFinite(lng) || !Number.isFinite(lat)) continue
      if (lng === 0 && lat === 0) continue
      bounds.extend(a.center)
    }
    if (bounds.isEmpty()) return
    map.fitBounds(bounds, { padding: 60, pitch: 55, bearing: -20, duration: 0 })
    fittedRef.current = true
  }, [assets])

  // Recolour for selection and preview.
  useEffect(() => {
    const map = mapRef.current
    if (!map || !mapReady) return

    const selectedColour = previewing ? C.intervene : C.selected
    const expr =
      selectedIds.length === 0
        ? STATUS_PAINT
        : ([
            'case',
            ['in', ['get', 'id'], ['literal', selectedIds]], selectedColour,
            STATUS_PAINT,
          ] as never)

    map.setPaintProperty('assets-3d', 'fill-extrusion-color', expr as never)
    map.setPaintProperty('area-fill', 'fill-color', expr as never)
    map.setPaintProperty('points-dot', 'circle-color', expr as never)
  }, [selectedIds, previewing, assets, mapReady])

  // A floating tag above each selected asset.
  useEffect(() => {
    const map = mapRef.current
    if (!map || !mapReady) return

    markersRef.current.forEach((m) => m.remove())
    markersRef.current = []

    selectedAssets.forEach((asset) => {
      const el = document.createElement('div')
      el.style.cssText = 'pointer-events:none'
      el.innerHTML = `
        <div style="
          display:flex;flex-direction:column;align-items:center;
          animation:popIn .3s cubic-bezier(.22,.8,.3,1) both">
          <div style="
            background:rgba(26,20,26,.92);border:1px solid ${C.selected};border-radius:9px;
            padding:7px 12px;color:#fff;font:600 11px/1 system-ui,sans-serif;
            letter-spacing:.06em;white-space:nowrap;
            box-shadow:0 0 18px rgba(33,150,243,.45),0 6px 16px rgba(0,0,0,.5);
            backdrop-filter:blur(4px)">${asset.name}</div>
          <div style="width:0;height:26px;border-left:1px dashed rgba(255,255,255,.55)"></div>
          <div style="width:9px;height:9px;border-radius:50%;background:#fff;
            box-shadow:0 0 0 4px rgba(33,150,243,.35)"></div>
        </div>
      `
      markersRef.current.push(
        new maplibregl.Marker({ element: el, anchor: 'bottom' })
          .setLngLat(asset.center)
          .addTo(map),
      )
    })

    return () => {
      markersRef.current.forEach((m) => m.remove())
      markersRef.current = []
    }
  }, [selectedIds, assets, mapReady])

  const zoomBy = (d: 1 | -1) =>
    mapRef.current?.easeTo({ zoom: (mapRef.current.getZoom() ?? 14) + d, duration: 320 })

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

        {selectedIds.length > 1 && (
          <span className="pop" style={{
            fontSize: 11, letterSpacing: '.1em', textTransform: 'uppercase', color: C.selected,
            border: `1px solid ${C.selected}`, borderRadius: 5, padding: '3px 9px',
            display: 'flex', alignItems: 'center', gap: 8,
          }}>
            {selectedIds.length} selected
            <button className="btn" onClick={closePanel}
              style={{ ...btn(false), padding: '1px 6px', fontSize: 10 }}>Clear</button>
          </span>
        )}

        <span style={{ flex: 1 }} />
        <span style={{ ...cap, marginRight: 4 }}>Horizon</span>
        {YEARS.map((y) => (
          <button
            key={y}
            className={`btn${year === y ? ' primary' : ''}`}
            onClick={() => setYear(y)}
            style={btn(year === y)}
          >
            {y}
          </button>
        ))}
      </header>

      {showComparison && analysis && (
        <ComparisonModal data={analysis} onClose={() => setShowComparison(false)} />
      )}

      <div style={{ display: 'flex', flex: 1, minHeight: 0 }}>
        <main style={{ position: 'relative', flex: 1 }}>
          <div ref={mapContainer} style={{ position: 'absolute', inset: 0 }} />
          <MapLegend preview={previewing} />
          <MapControls bearing={bearing} tilted={tilted} onZoom={zoomBy} onCompass={resetNorth} onTilt={toggleTilt} />
        </main>

        <aside className="panel" style={{
          width: 420, flex: 'none', padding: 22, overflowY: 'auto',
          background: C.panel, borderLeft: `1px solid ${C.line}`,
        }}>
          {primary ? (
            <AssetPanel
              assets={selectedAssets}
              question={question} setQuestion={setQuestion}
              asked={asked} analysis={analysis} loading={loading} error={error}
              onAsk={ask}
              previewing={previewing}
              onPreview={() => setPreviewing(true)}
              onClearPreview={() => setPreviewing(false)}
              onSimulate={simulate} onClose={closePanel}
            />
          ) : (
            <DeadspaceList assets={assets} onPick={(a) => selectOnly(a.id)} />
          )}
        </aside>
      </div>
    </div>
  )
}