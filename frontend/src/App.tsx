import { useEffect, useRef, useState } from 'react'
import * as maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'
import { C, cap, btn } from './theme'
import { MapLegend, MapControls } from './components/ui'
import { DeadspaceList } from './components/DeadspaceList'
import { AssetPanel } from './components/AssetPanel'
import { ComparisonModal } from './components/ComparisonModal'
import { HistoryPanel } from './components/HistoryPanel'
import { fetchProfiles, fetchGeometry, runAnalysis } from './api'
import type { Asset, AssetProfile, AnalyzeResult } from './types'
import type { Feature, FeatureCollection, Geometry } from 'geojson'

maplibregl.setWorkerUrl(workerUrl)

const YEARS = [2026, 2027, 2028, 2030, 2033]
const METRES_PER_FLOOR = 3.5
const EMPTY: FeatureCollection = { type: 'FeatureCollection', features: [] }

export type AnalyzeHistoryItem = {
  id: string
  result: AnalyzeResult
  status: 'pending' | 'accepted' | 'declined'
}

function centroidOf(geometry: Geometry): [number, number] {
  if (!geometry) return [0, 0]
  if (geometry.type === 'Point') return [geometry.coordinates[0], geometry.coordinates[1]]
  const ring = geometry.type === 'Polygon' ? geometry.coordinates[0] : geometry.type === 'MultiPolygon' ? geometry.coordinates[0][0] : null
  if (!ring || ring.length === 0) return [0, 0]
  let x = 0, y = 0
  for (const p of ring) { x += p[0]; y += p[1] }
  return [x / ring.length, y / ring.length]
}

function heightOf(profile: AssetProfile | null): number {
  const floor = profile?.physical.floor_area_m2
  const land = profile?.physical.land_area_m2
  if (!floor || !land || land <= 0) return 0
  const floors = Math.max(1, Math.round(floor / land))
  return Math.min(floors, 40) * METRES_PER_FLOOR
}

const STATUS_PAINT: maplibregl.ExpressionSpecification = [
  'match', ['get', 'status'],
  'healthy', '#3fb27f',
  'monitor', '#f7931d',
  'improvement_opportunity', '#f7931d',
  'development_risk', '#f15c22',
  'deadspace_candidate', '#d71920',
  'underperforming_facility', '#d71920',
  'intervened', '#00d2ff',
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
  
  const [history, setHistory] = useState<AnalyzeHistoryItem[]>(() => {
    try { return JSON.parse(localStorage.getItem('lm_history') || '[]') } catch { return [] }
  })
  const [activeRunId, setActiveRunId] = useState<string | undefined>(undefined)
  const [showHistory, setShowHistory] = useState(false)

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

  const selectedAssets = selectedIds.map((id) => assets.find((a) => a.id === id)).filter((a): a is Asset => !!a)
  const primary = selectedAssets[0] ?? null

  useEffect(() => {
    localStorage.setItem('lm_history', JSON.stringify(history.slice(0, 10)))
  }, [history])

  function reset() {
    setAnalysis(null); setAsked(''); setError(null)
    setPreviewing(false); setShowComparison(false); setActiveRunId(undefined)
  }

  function selectOnly(id: string) {
    setSelectedIds([id]); setQuestion(''); reset()
    const a = assetsRef.current.find((x) => x.id === id)
    if (a) mapRef.current?.easeTo({ center: a.center, zoom: 17.5, pitch: 58, duration: 900 })
  }

  function toggleSelect(id: string) {
    setSelectedIds((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id])
    reset()
  }

  function closePanel() { setSelectedIds([]); setQuestion(''); reset() }

  async function ask() {
    if (selectedAssets.length === 0) return
    const q = question.trim() || 'What should we do with these assets?'
    setLoading(true); setError(null); setAsked(q)
    try {
      const res = await runAnalysis(q, selectedIds)
      setAnalysis(res)
      setQuestion('')
      
      const newItem: AnalyzeHistoryItem = { id: res.run_id || Date.now().toString(), result: res, status: 'pending' }
      setHistory(prev => [newItem, ...prev])
      setActiveRunId(undefined)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally { setLoading(false) }
  }

  const updateHistoryStatus = (id: string, status: 'accepted' | 'declined') => {
    setHistory(prev => prev.map(h => h.id === id ? { ...h, status } : h))
    if (status === 'declined' && activeRunId === id) {
      setActiveRunId(undefined); setPreviewing(false)
    } else if (status === 'accepted') {
      setActiveRunId(id)
    }
  }

  // Clear all history and reset map state
  const clearHistory = () => {
    if (window.confirm("Are you sure you want to clear all analysis history?")) {
      setHistory([])
      setActiveRunId(undefined)
      setPreviewing(false)
      localStorage.removeItem('lm_history')
    }
  }

  const handleSelectHistory = (item: AnalyzeHistoryItem) => {
    setSelectedIds(item.result.assets_analysis.map(a => a.asset_id))
    setAnalysis(item.result)
    setAsked(item.result.decision.reasoning || '')
    setShowHistory(false)
    setActiveRunId(item.status === 'accepted' ? item.id : undefined)
  }

  useEffect(() => {
    fetchProfiles().then(setProfilesData).catch((e) => setError(e.message))
  }, [])

  // Fetch Geometry and extract Intervention Points for the native layer
  useEffect(() => {
    if (Object.keys(profilesData).length === 0) return

    fetchGeometry(activeRunId, year)
      .then((geo) => {
        const list: Asset[] = []
        const buildingFeatures: Feature[] = []
        const areaFeatures: Feature[] = []
        const pointFeatures: Feature[] = []
        const interventionPoints: Feature[] = [] // Store intervention centers for native layer

        for (const f of geo.features) {
          const p = (f.properties ?? {}) as Record<string, unknown>
          const id = String(p.asset_id ?? '')
          if (!id || f.geometry.type === 'LineString' || f.geometry.type === 'MultiLineString') continue

          const baseProfile = profilesData[id] ?? null
          let finalProfile = baseProfile ? JSON.parse(JSON.stringify(baseProfile)) : null
          const mapStatus = String(p.map_status ?? 'healthy')

          if (finalProfile && p.metrics_json) {
            try {
              const metrics = JSON.parse(p.metrics_json as string)
              if (metrics.occupancy !== undefined) {
                finalProfile.social.occupancy_rate = metrics.occupancy
                finalProfile.social.utilisation_rate = metrics.occupancy
              }
              if (metrics.noi_rm !== undefined) finalProfile.financial.noi_rm = metrics.noi_rm
              if (metrics.carbon_operational_tco2e !== undefined) {
                finalProfile.environmental.carbon_operational_tco2e = metrics.carbon_operational_tco2e
                finalProfile.environmental.stranded_carbon_ratio = metrics.stranded_carbon_ratio
              }
            } catch (e) {}
          }

          const backendFlags = (p.flags as string[]) || []
          const backendUrgency = Number(p.urgency_index ?? 0)
          let dynamicDiagnosis = finalProfile?.deadspace_diagnosis ?? null
          if (dynamicDiagnosis) {
            dynamicDiagnosis = { ...dynamicDiagnosis, status: mapStatus as any, flags: backendFlags, urgency_index: backendUrgency }
          }

          const backendHeight = Number(p.height)
          const finalHeight = !Number.isNaN(backendHeight) && backendHeight > 0 ? backendHeight : heightOf(finalProfile)
          const center = centroidOf(f.geometry)

          list.push({
            id, name: finalProfile?.identity.asset_name ?? id, subtype: finalProfile?.identity.subtype ?? null,
            assetType: finalProfile?.identity.asset_type ?? 'unknown', mapStatus,
            profile: finalProfile, diagnosis: dynamicDiagnosis, center, height: finalHeight,
          })

          const tagged: Feature = { ...f, properties: { ...f.properties, id, status: mapStatus, height: finalHeight } }

          if (f.geometry.type === 'Point') pointFeatures.push(tagged)
          else if (finalHeight > 0) buildingFeatures.push(tagged)
          else areaFeatures.push(tagged)

          // Extract intervention centers to render native MapLibre symbols
          if (mapStatus === 'intervened' && center[0] !== 0) {
            interventionPoints.push({
              type: 'Feature',
              geometry: { type: 'Point', coordinates: center },
              properties: { title: 'INTERVENTION' }
            })
          }
        }

        buildingsRef.current = { type: 'FeatureCollection', features: buildingFeatures }
        areaRef.current = { type: 'FeatureCollection', features: areaFeatures }
        pointsRef.current = { type: 'FeatureCollection', features: pointFeatures }

        assetsRef.current = list
        setAssets(list)
        
        const map = mapRef.current
        if (map && mapReady) {
          ;(map.getSource('assets') as maplibregl.GeoJSONSource | undefined)?.setData(buildingsRef.current)
          ;(map.getSource('area') as maplibregl.GeoJSONSource | undefined)?.setData(areaRef.current)
          ;(map.getSource('points') as maplibregl.GeoJSONSource | undefined)?.setData(pointsRef.current)
          
          // Update native intervention layer
          const intSource = map.getSource('interventions') as maplibregl.GeoJSONSource
          if (intSource) intSource.setData({ type: 'FeatureCollection', features: interventionPoints })
        }
      })
      .catch((e) => setError(e.message))
  }, [year, profilesData, mapReady, activeRunId])

  useEffect(() => {
    if (!mapContainer.current) return
    const map = new maplibregl.Map({
      container: mapContainer.current,
      style: {
        version: 8,
        sources: { osm: { type: 'raster', tiles: ['https://tiles.stadiamaps.com/tiles/alidade_smooth_dark/{z}/{x}/{y}.png'], tileSize: 256 } },
        layers: [{ id: 'osm', type: 'raster', source: 'osm' }],
      },
      center: [101.528, 3.112], zoom: 14, pitch: 55, bearing: -20, maxPitch: 80,
    })

    mapRef.current = map
    map.on('rotate', () => setBearing(map.getBearing()))
    map.on('pitch', () => setTilted(map.getPitch() > 10))

    map.on('load', () => {
      map.setSky({ 'sky-color': '#1a1320', 'horizon-color': '#4a3a48', 'sky-horizon-blend': 0.6 })
      map.addSource('assets', { type: 'geojson', data: EMPTY })
      map.addSource('area', { type: 'geojson', data: EMPTY })
      map.addSource('points', { type: 'geojson', data: EMPTY })
      map.addSource('interventions', { type: 'geojson', data: EMPTY }) // 👈 Native Source

      map.addLayer({ id: 'area-fill', type: 'fill', source: 'area', paint: { 'fill-color': STATUS_PAINT as never, 'fill-opacity': 0.35 } })
      map.addLayer({
        id: 'assets-3d', type: 'fill-extrusion', source: 'assets',
        paint: {
          'fill-extrusion-color': STATUS_PAINT as never,
          'fill-extrusion-height': ['coalesce', ['get', 'height'], 8] as never,
          'fill-extrusion-vertical-gradient': true,
          'fill-extrusion-opacity': 0.92,
        },
      })
      map.addLayer({ id: 'points-dot', type: 'circle', source: 'points', paint: { 'circle-radius': ['interpolate', ['linear'], ['zoom'], 13, 4, 18, 11] as never, 'circle-color': STATUS_PAINT as never, 'circle-stroke-width': 1.5, 'circle-stroke-color': 'rgba(0,0,0,.55)' } })

      // 👈 Native Intervention Layer (Symbol + Pulse)
      map.addLayer({
        id: 'intervention-labels',
        type: 'symbol',
        source: 'interventions',
        layout: {
          'text-field': '🚧 INTERVENTION',
          'text-size': 11,
          'text-offset': [0, -2.5],
          'text-anchor': 'bottom',
          'text-allow-overlap': true,
        },
        paint: {
          'text-color': '#00d2ff',
          'text-halo-color': '#000',
          'text-halo-width': 1.5,
        }
      })
      // Add a glowing circle at the base
      map.addLayer({
        id: 'intervention-pulse',
        type: 'circle',
        source: 'interventions',
        paint: {
          'circle-radius': 12,
          'circle-color': '#00d2ff',
          'circle-opacity': 0.4,
          'circle-stroke-width': 2,
          'circle-stroke-color': '#00d2ff',
        }
      })

      // Animate the pulse radius (breathing effect)
      let radius = 12;
      let growing = true;
      function animatePulse() {
        if (!map.getLayer('intervention-pulse')) return;
        radius += growing ? 0.1 : -0.1;
        if (radius > 26) growing = false;
        if (radius < 12) growing = true;
        map.setPaintProperty('intervention-pulse', 'circle-radius', radius);
        map.setPaintProperty('intervention-pulse', 'circle-opacity', 0.4 - (radius - 12) / 60);
        requestAnimationFrame(animatePulse);
      }
      animatePulse();

      const onClick = (e: maplibregl.MapLayerMouseEvent) => {
        const id = e.features?.[0]?.properties?.id
        if (typeof id !== 'string') return
        if (e.originalEvent.ctrlKey || e.originalEvent.metaKey || e.originalEvent.shiftKey) toggleSelect(id)
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

  const fittedRef = useRef(false)
  useEffect(() => {
    const map = mapRef.current
    if (!map || fittedRef.current || assets.length === 0) return
    const bounds = new maplibregl.LngLatBounds()
    for (const a of assets) {
      if (Number.isFinite(a.center[0]) && a.center[0] !== 0) bounds.extend(a.center)
    }
    if (!bounds.isEmpty()) { map.fitBounds(bounds, { padding: 60, pitch: 55, bearing: -20, duration: 0 }); fittedRef.current = true }
  }, [assets])
  // Selected assets turn blue, or intervention-blue while previewing.
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

  // A floating name tag above each selected asset.
  useEffect(() => {
    const map = mapRef.current
    if (!map || !mapReady) return

    markersRef.current.forEach((m) => m.remove())
    markersRef.current = []

    selectedAssets.forEach((asset) => {
      if (!Number.isFinite(asset.center[0]) || asset.center[0] === 0) return

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

  return (
    <div style={{ display: 'flex', flexDirection: 'column', width: '100vw', height: '100vh', background: C.bg, color: C.text, fontFamily: 'system-ui', overflow: 'hidden' }}>
      <style>{`
        @keyframes bounce { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-10px); } }
        .bounce-marker { animation: bounce 1.5s infinite ease-in-out; }

        /* Force custom scrollbar and hide arrows */
        ::-webkit-scrollbar {
          width: 6px !important;
          height: 6px !important;
        }
        ::-webkit-scrollbar-button {
          display: none !important;
          height: 0 !important;
          width: 0 !important;
        }
        ::-webkit-scrollbar-thumb {
          background: #3e333d !important;
          border-radius: 4px !important;
        }
        ::-webkit-scrollbar-thumb:hover {
          background: #5a4f59 !important;
        }
        ::-webkit-scrollbar-track {
          background: transparent !important;
        }
      `}</style>
      <header style={{ height: 58, flex: 'none', padding: '0 22px', borderBottom: `1px solid ${C.line}`, display: 'flex', alignItems: 'center', gap: 14, background: '#241c23' }}>
        <strong style={{ fontSize: 14, letterSpacing: '.14em' }}>LIVING MASTERPLAN</strong>
        <span style={{ fontSize: 13, color: C.muted }}>Bukit Jelutong</span>
        
        <button className={`btn ${showHistory ? 'primary' : ''}`} onClick={() => setShowHistory(!showHistory)} style={{...btn(showHistory), marginLeft: 20}}>
          History ({history.length})
        </button>

        <span style={{ flex: 1 }} />
        <span style={{ ...cap, marginRight: 4 }}>Horizon</span>
        {YEARS.map((y) => (
          <button key={y} className={`btn${year === y ? ' primary' : ''}`} onClick={() => setYear(y)} style={btn(year === y)}>{y}</button>
        ))}
      </header>

      {showComparison && analysis && <ComparisonModal data={analysis} onClose={() => setShowComparison(false)} />}

      <div style={{ display: 'flex', flex: 1, minHeight: 0 }}>
        <main style={{ position: 'relative', flex: 1 }}>
          <div ref={mapContainer} style={{ position: 'absolute', inset: 0 }} />
          <MapLegend preview={previewing} />
          <MapControls bearing={bearing} tilted={tilted} onZoom={(d) => mapRef.current?.easeTo({ zoom: (mapRef.current.getZoom() ?? 14) + d })} onCompass={() => mapRef.current?.easeTo({ bearing: 0, pitch: 55 })} onTilt={() => mapRef.current?.easeTo({ pitch: mapRef.current.getPitch() > 10 ? 0 : 58 })} />
        </main>

        <aside style={{ width: 440, flex: 'none', padding: 22, overflowY: 'auto', overflowX: 'hidden', background: C.panel, borderLeft: `1px solid ${C.line}` }}>
          {showHistory ? (
            <HistoryPanel 
              history={history} 
              onClose={() => setShowHistory(false)}
              onUpdateStatus={updateHistoryStatus}
              onPreview={(id) => { setActiveRunId(id); setShowHistory(false); }}
              activeRunId={activeRunId}
              onSelectHistory={handleSelectHistory}
              onClear={clearHistory}
            />
          ) : primary ? (
            <AssetPanel
              assets={selectedAssets} question={question} setQuestion={setQuestion} asked={asked} analysis={analysis} loading={loading} error={error}
              onAsk={ask} previewing={previewing} 
              onPreview={() => { if (analysis) { setActiveRunId(analysis.run_id); setPreviewing(true); } }}
              onClearPreview={() => { setActiveRunId(undefined); setPreviewing(false); }} 
              onSimulate={() => analysis && setShowComparison(true)} onClose={closePanel}
            />
          ) : (
            <DeadspaceList assets={assets} onPick={(a) => selectOnly(a.id)} />
          )}
        </aside>
      </div>
    </div>
  )
}