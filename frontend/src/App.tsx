import { useEffect, useRef, useState } from 'react'
import * as maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'
import { C, cap, btn, mono } from './theme'
import { MapLegend, MapControls } from './components/ui'
import { DeadspaceList } from './components/DeadspaceList'
import { AssetPanel } from './components/AssetPanel'
import { ComparisonModal } from './components/ComparisonModal'
import { HistoryPanel } from './components/HistoryPanel'
import { fetchProfiles, fetchGeometry, runAnalysis } from './api'
import type { Asset, AssetProfile, AnalyzeResult } from './types'
import type { Feature, FeatureCollection, Geometry } from 'geojson'

maplibregl.setWorkerUrl(workerUrl)

// Flip to false to restore the original rendering exactly.
const REALISTIC = true

const SOUND = true

// One decoded buffer, played on each selection. No network hit per click.
let clickBuf: AudioBuffer | null = null
let audioCtx: AudioContext | null = null

function playClick() {
  if (!SOUND || !clickBuf || !audioCtx) return
  if (audioCtx.state === 'suspended') audioCtx.resume()
  const src = audioCtx.createBufferSource()
  const gain = audioCtx.createGain()
  gain.gain.value = 0.35
  src.buffer = clickBuf
  src.connect(gain).connect(audioCtx.destination)
  src.start()
}

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

// Generate a smooth bezier curve between two coordinates
function generateArc(start: [number, number], end: [number, number]): [number, number][] {
  const midX = (start[0] + end[0]) / 2
  const midY = (start[1] + end[1]) / 2
  const dx = end[0] - start[0]
  const dy = end[1] - start[1]
  const dist = Math.sqrt(dx * dx + dy * dy)
  const curvature = dist * 0.2
  const ctrlX = midX - dy * (curvature / dist)
  const ctrlY = midY + dx * (curvature / dist)

  const points: [number, number][] = []
  for (let t = 0; t <= 1; t += 0.05) {
    const x = (1 - t) ** 2 * start[0] + 2 * (1 - t) * t * ctrlX + t ** 2 * end[0]
    const y = (1 - t) ** 2 * start[1] + 2 * (1 - t) * t * ctrlY + t ** 2 * end[1]
    points.push([x, y])
  }
  return points
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

function mix(hex: string, toward: string, t: number): string {
  const a = parseInt(hex.slice(1), 16), b = parseInt(toward.slice(1), 16)
  const ch = (s: number) => Math.round(((a >> s) & 255) * (1 - t) + ((b >> s) & 255) * t)
  return '#' + ((ch(16) << 16) | (ch(8) << 8) | ch(0)).toString(16).padStart(6, '0')
}

const STATUS_HEX: Record<string, string> = {
  healthy: '#3fb27f', monitor: '#f7931d', improvement_opportunity: '#f7931d',
  development_risk: '#f15c22', deadspace_candidate: '#d71920', underperforming_facility: '#d71920',
  intervened: '#00d2ff', vacant: '#9e9e9e',
}
const STATUS_FALLBACK = '#5a4f59'
const H = ['coalesce', ['get', 'height'], 8]

const statusMatch = (fn: (hex: string) => unknown) =>
  ['match', ['get', 'status'],
    ...Object.entries(STATUS_HEX).flatMap(([k, hex]) => [k, fn(hex)]),
    fn(STATUS_FALLBACK),
  ] as never

// Same hue per status, darker at ground level, slightly lighter for towers.
const BODY_PAINT = statusMatch((hex) => [
  'interpolate', ['linear'], H,
  0, mix(hex, '#000000', 0.22),
  20, hex,
  60, mix(hex, '#ffffff', 0.10),
])
const ROOF_PAINT = statusMatch((hex) => mix(hex, '#ffffff', 0.35))

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

  const [hint, setHint] = useState(false)
  const hintTimer = useRef<number | undefined>(undefined)

  function pokeHint() {
    setHint(true)
    window.clearTimeout(hintTimer.current)
    hintTimer.current = window.setTimeout(() => setHint(false), 1800)
  }

  const selectedAssets = selectedIds.map((id) => assets.find((a) => a.id === id)).filter((a): a is Asset => !!a)
  const primary = selectedAssets[0] ?? null

  useEffect(() => {
    localStorage.setItem('lm_history', JSON.stringify(history.slice(0, 10)))
  }, [history])

  // Sync selectedIds when activeRunId changes
  useEffect(() => {
    if (activeRunId) {
      const item = history.find(h => h.id === activeRunId)
      if (item) {
        setSelectedIds(item.result.assets_analysis.map(a => a.asset_id))
      }
    }
  }, [activeRunId, history])

  function reset() {
    setAnalysis(null); setAsked(''); setError(null)
    setPreviewing(false); setShowComparison(false); setActiveRunId(undefined)
  }

  function selectOnly(id: string) {
    setSelectedIds([id]); setQuestion(''); reset()
    playClick()
    const a = assetsRef.current.find((x) => x.id === id)
    if (!a) return
    const m = mapRef.current
    if (!m) return
        if (REALISTIC) {
      // Swing the camera round to a 3/4 view of the building, and lift the
      // target up the screen so the whole height sits in frame under pitch.
      const tall = (a.height ?? 0) > 25

      // Swing toward whichever side the building is already on, so the camera
      // turns the short way round instead of always sweeping left.
      const w = m.getCanvas().clientWidth
      const sx = m.project(a.center).x
      const off = (sx - w / 2) / (w / 2)          // -1 = far left, +1 = far right
      const swing = Math.abs(off) < 0.12
        ? 28                                      // already centred: pick a side
        : Math.sign(off) * (18 + Math.abs(off) * 22)

      m.flyTo({
        center: a.center,
        zoom: tall ? 17.2 : 17.8,
        pitch: tall ? 62 : 56,
        bearing: m.getBearing() + swing,
        offset: [0, tall ? -110 : -55],
        curve: 1.5,
        speed: 0.7,
        essential: true,
      })
    } else {
      m.easeTo({ center: a.center, zoom: 17.5, pitch: 58, duration: 900 })
    }
  }

  function toggleSelect(id: string) {
    setSelectedIds((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id])
    playClick()
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

  const clearHistory = () => {
    if (window.confirm("Are you sure you want to clear all analysis history?")) {
      setHistory([]); setActiveRunId(undefined); setPreviewing(false); localStorage.removeItem('lm_history')
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

  useEffect(() => {
    if (Object.keys(profilesData).length === 0) return

    fetchGeometry(activeRunId, year)
      .then((geo) => {
        const list: Asset[] = []
        const buildingFeatures: Feature[] = []
        const areaFeatures: Feature[] = []
        const pointFeatures: Feature[] = []

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
            // Phase 4c — for every year (not just 2026), overlay the
            // full B6 diagnostic payload from the map endpoint.
            // evidence and contributing_factors are year-specific:
            // a park that failed on green_per_capita in 2026 may be
            // failing on canopy loss by 2033, and the AssetPanel
            // must reflect that.
            let dynamicEvidence = dynamicDiagnosis.evidence
            let dynamicFactors = dynamicDiagnosis.contributing_factors
            if (p.evidence_json) {
              try {
                const ev = JSON.parse(p.evidence_json as string)
                if (Array.isArray(ev) && ev.length > 0) dynamicEvidence = ev
              } catch { /* leave as 2026 value */ }
            }
            if (p.factors_json) {
              try {
                const fac = JSON.parse(p.factors_json as string)
                if (Array.isArray(fac) && fac.length > 0) dynamicFactors = fac
              } catch { /* leave as 2026 value */ }
            }
            dynamicDiagnosis = {
              ...dynamicDiagnosis,
              status: mapStatus as any,
              flags: backendFlags,
              urgency_index: backendUrgency,
              evidence: dynamicEvidence,
              contributing_factors: dynamicFactors,
            }
          }

          const backendHeight = Number(p.height)
          const finalHeight = !Number.isNaN(backendHeight) && backendHeight > 0 ? backendHeight : heightOf(finalProfile)
          const center = centroidOf(f.geometry)

          let displayId = id;
          if (id.startsWith('A-')) displayId = id.replace('A-', 'FAC-');
          if (id.startsWith('G-')) displayId = id.replace('G-', 'GRN-');

          let displaySubtype = finalProfile?.identity.subtype ?? null;
          let displayName = finalProfile?.identity.asset_name ?? displayId;

          const isMixedUse = 
            (finalProfile?.subunits && finalProfile.subunits.length > 1) || 
            (dynamicDiagnosis?.evidence && dynamicDiagnosis.evidence.some(e => e.includes('Subtype occupancy:')));

          if (isMixedUse) {
             displaySubtype = "Mixed-Use Commercial";
             const lettable = finalProfile?.physical.lettable_area_m2 ?? 0;
             if (lettable > 4000) {
                displayName = `Mixed-Use Hub ${displayId}`;
             } else if (lettable > 1000) {
                displayName = `Shoplot Row ${displayId}`;
             } else {
                displayName = `Commercial Block ${displayId}`;
             }
          } else if (finalProfile?.identity.asset_type === 'residential') {
             const sub = finalProfile.identity.subtype || 'residential';
             const prettySub = sub.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
             displayName = `${prettySub} ${displayId}`;
             displaySubtype = "Residential";
          } else if (finalProfile?.identity.asset_type === 'community_facility') {
             displaySubtype = finalProfile.identity.subtype ? 
               finalProfile.identity.subtype.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()) : 
               "Community Facility";
             displayName = `${displaySubtype} ${displayId}`;
          }

          list.push({
            id, 
            name: displayName, 
            subtype: displaySubtype, 
            assetType: finalProfile?.identity.asset_type ?? 'unknown', 
            mapStatus,
            profile: finalProfile, 
            diagnosis: dynamicDiagnosis, 
            center, 
            height: finalHeight,
          })

          const tagged: Feature = { ...f, properties: { ...f.properties, id, status: mapStatus, height: finalHeight } }

          if (f.geometry.type === 'Point') pointFeatures.push(tagged)
          else if (finalHeight > 0) buildingFeatures.push(tagged)
          else areaFeatures.push(tagged)
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
        layers: [{
          id: 'osm', type: 'raster', source: 'osm',
          ...(REALISTIC ? { paint: {
            'raster-hue-rotate': 80,
            'raster-saturation': -0.35,
            'raster-brightness-max': 0.85,
            'raster-contrast': 0.1,
          } } : {}),
        }],
      },
      center: [101.528, 3.112], zoom: 14, pitch: 55, bearing: -20, maxPitch: 80,
      ...(REALISTIC ? { canvasContextAttributes: { antialias: true } } : {}),
    })

    mapRef.current = map
    map.on('rotate', () => setBearing(map.getBearing()))
    map.on('pitch', () => setTilted(map.getPitch() > 10))
    map.on('load', () => {
      map.setSky(REALISTIC
        ? {
            'sky-color': '#1c141b',
            'horizon-color': '#6b4652',
            'sky-horizon-blend': 0.75,
            'fog-color': '#2b212a',
            'horizon-fog-blend': 0.5,
          }
        : { 'sky-color': '#1a1320', 'horizon-color': '#4a3a48', 'sky-horizon-blend': 0.6 })
      map.addSource('assets', { type: 'geojson', data: EMPTY })
      map.addSource('area', { type: 'geojson', data: EMPTY })
      map.addSource('points', { type: 'geojson', data: EMPTY })
      map.addSource('interventions-points', { type: 'geojson', data: EMPTY })
      map.addSource('interventions-arcs', { type: 'geojson', data: EMPTY })

      // Directional light so faces shade differently by orientation.
      map.setLight(REALISTIC
        ? { anchor: 'map', color: '#f4f0ec', intensity: 0.4, position: [1.2, 240, 40] }
        : { anchor: 'viewport', color: '#ffffff', intensity: 0.42, position: [1.4, 200, 28] })

      map.addLayer({ id: 'area-fill', type: 'fill', source: 'area', paint: { 'fill-color': STATUS_PAINT as never, 'fill-opacity': 0.35 } })
      if (REALISTIC) {
        map.addLayer({
          id: 'assets-contact-shadow', type: 'line', source: 'assets',
          paint: {
            'line-color': '#000000',
            'line-opacity': 0.45,
            'line-width': ['interpolate', ['linear'], ['zoom'], 14, 3, 18, 14] as never,
            'line-blur': ['interpolate', ['linear'], ['zoom'], 14, 2, 18, 8] as never,
          },
        })
      
        // Fake cast shadows: footprint shifted away from the sun (light at 240°, so shadows point to 60°).
        // Three height bands, so taller buildings throw longer shadows.
        const SHADOW_BANDS: Array<[string, unknown, number[], number[]]> = [
          ['assets-shadow-low',  ['<', H, 12],                           [0.4, -0.25], [6, -3.5]],
          ['assets-shadow-mid',  ['all', ['>=', H, 12], ['<', H, 30]],   [0.9, -0.55], [15, -8.5]],
          ['assets-shadow-tall', ['>=', H, 30],                          [1.8, -1.05], [29, -17]],
        ]
        for (const [id, filter, z14, z18] of SHADOW_BANDS) {
          map.addLayer({
            id, type: 'fill', source: 'assets', filter: filter as never,
            paint: {
              'fill-color': '#120c11',
              'fill-opacity': 0.38,
              'fill-translate-anchor': 'map',
              'fill-translate': ['interpolate', ['exponential', 2], ['zoom'],
                14, ['literal', z14], 18, ['literal', z18]] as never,
            },
          })
        }
      }
      map.addLayer({
        id: 'assets-3d', type: 'fill-extrusion', source: 'assets',
        paint: {
          'fill-extrusion-color': (REALISTIC ? BODY_PAINT : STATUS_PAINT) as never,
          'fill-extrusion-height': ['coalesce', ['get', 'height'], 8] as never,
          'fill-extrusion-vertical-gradient': true,
          'fill-extrusion-opacity': REALISTIC ? 1 : 0.92,
        },
      })
      if (REALISTIC) {
        map.addLayer({
          id: 'assets-roof', type: 'fill-extrusion', source: 'assets',
          paint: {
            'fill-extrusion-color': ROOF_PAINT,
            'fill-extrusion-base': H as never,
            'fill-extrusion-height': ['+', H, 0.8] as never,
            'fill-extrusion-vertical-gradient': false,
            'fill-extrusion-opacity': 1,
          },
        })
      }
      map.addLayer({ id: 'points-dot', type: 'circle', source: 'points', paint: { 'circle-radius': ['interpolate', ['linear'], ['zoom'], 13, 4, 18, 11] as never, 'circle-color': STATUS_PAINT as never, 'circle-stroke-width': 1.5, 'circle-stroke-color': 'rgba(0,0,0,.55)' } })

      // Intervention Arc Layer
      map.addLayer({
        id: 'intervention-arcs-line',
        type: 'line',
        source: 'interventions-arcs',
        layout: { 'line-join': 'round', 'line-cap': 'round' },
        paint: {
          'line-color': '#a855f7',
          'line-width': 2,
          'line-dasharray': [2, 2],
          'line-opacity': 0.8,
        }
      })

      // Intervention Point Layers
      map.addLayer({
        id: 'intervention-pulse-primary',
        type: 'circle',
        source: 'interventions-points',
        filter: ['==', ['get', 'role'], 'primary'],
        paint: {
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 12, 8, 18, 24],
          'circle-color': '#00d2ff',
          'circle-opacity': 0.3,
          'circle-stroke-width': 2,
          'circle-stroke-color': '#00d2ff',
        }
      })

      map.addLayer({
        id: 'intervention-pulse-catalytic',
        type: 'circle',
        source: 'interventions-points',
        filter: ['==', ['get', 'role'], 'catalytic'],
        paint: {
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 12, 8, 18, 24],
          'circle-color': '#a855f7',
          'circle-opacity': 0.3,
          'circle-stroke-width': 2,
          'circle-stroke-color': '#a855f7',
        }
      })

      map.addLayer({
        id: 'intervention-labels',
        type: 'symbol',
        source: 'interventions-points',
        layout: {
          'text-field': ['get', 'label'],
          'text-size': 11,
          'text-offset': [0, -2.5],
          'text-anchor': 'bottom',
          'text-allow-overlap': true,
        },
        paint: {
          'text-color': ['match', ['get', 'role'], 'catalytic', '#a855f7', '#00d2ff'],
          'text-halo-color': '#000',
          'text-halo-width': 1.5,
        }
      })

      let radius = 10; let growing = true;
      function animatePulse() {
        if (!map.getLayer('intervention-pulse-primary')) return;
        radius += growing ? 0.05 : -0.05;
        if (radius > 20) growing = false;
        if (radius < 10) growing = true;
        map.setPaintProperty('intervention-pulse-primary', 'circle-radius', radius);
        map.setPaintProperty('intervention-pulse-catalytic', 'circle-radius', radius);
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

  // Effect to update ALL accepted and previewing interventions permanently
  useEffect(() => {
    const map = mapRef.current
    if (!map || !mapReady) return

    const pointFeatures: Feature[] = []
    const arcFeatures: Feature[] = []

    // 1. Gather interventions from ALL accepted history + current active preview
    const activeAndAccepted = history.filter(h => h.status === 'accepted' || h.id === activeRunId)
    
    activeAndAccepted.forEach(item => {
      const interventions = (item.result as any)?.interventions || []
      
      interventions.forEach((intv: any) => {
        const target = assets.find(x => x.id === intv.target_asset_id)
        
        // Mark the ACTUAL WORKING SITE
        if (target && Number.isFinite(target.center[0]) && target.center[0] !== 0) {
          const isCatalytic = intv.role === 'catalytic'
          pointFeatures.push({
            type: 'Feature',
            geometry: { type: 'Point', coordinates: target.center },
            properties: { 
              role: intv.role, 
              label: isCatalytic ? '✨ CATALYTIC WORKS' : '🚧 PRIMARY WORKS'
            }
          })
        }

        // Draw the ARC from Working Site to Beneficiary
        if (intv.role === 'catalytic' && intv.beneficiary_asset_id) {
          const beneficiary = assets.find(x => x.id === intv.beneficiary_asset_id)
          if (target && beneficiary && target.center[0] !== 0 && beneficiary.center[0] !== 0) {
            const arcCoords = generateArc(target.center, beneficiary.center)
            arcFeatures.push({
              type: 'Feature',
              geometry: { type: 'LineString', coordinates: arcCoords },
              properties: {}
            })
          }
        }
      })
    })

    const pSource = map.getSource('interventions-points') as maplibregl.GeoJSONSource
    if (pSource) pSource.setData({ type: 'FeatureCollection', features: pointFeatures })

    const aSource = map.getSource('interventions-arcs') as maplibregl.GeoJSONSource
    if (aSource) aSource.setData({ type: 'FeatureCollection', features: arcFeatures })
    
  }, [assets, selectedIds, activeRunId, mapReady, history])

  // Load and decode the click sound once. Browsers block audio until the user
  // interacts with the page, so the context is created on first click.
  useEffect(() => {
    if (!SOUND) return
    let dead = false
    const arm = async () => {
      if (!audioCtx) audioCtx = new AudioContext()
      if (audioCtx.state === 'suspended') await audioCtx.resume()
      if (clickBuf || dead) return
      try {
        const buf = await (await fetch('/click.mp3')).arrayBuffer()
        const decoded = await audioCtx.decodeAudioData(buf)
        if (!dead) clickBuf = decoded
      } catch { /* no sound is fine */ }
    }
    window.addEventListener('pointerdown', arm)
    return () => { dead = true; window.removeEventListener('pointerdown', arm) }
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

    const withSel = (base: unknown, sel: string) =>
      selectedIds.length === 0 ? base : ['case', ['in', ['get', 'id'], ['literal', selectedIds]], sel, base]
    if (REALISTIC) {
      map.setPaintProperty('assets-3d', 'fill-extrusion-color', withSel(BODY_PAINT, selectedColour) as never)
      map.setPaintProperty('assets-roof', 'fill-extrusion-color', withSel(ROOF_PAINT, mix(selectedColour, '#FCFBF4', 0.15)) as never)
    } else {
      map.setPaintProperty('assets-3d', 'fill-extrusion-color', expr as never)
    }    map.setPaintProperty('area-fill', 'fill-color', expr as never)
    map.setPaintProperty('points-dot', 'circle-color', expr as never)
  }, [selectedIds, previewing, assets, mapReady])

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
        <div style="display:flex;flex-direction:column;align-items:center;animation:popIn .3s cubic-bezier(.22,.8,.3,1) both">
          <div style="background:rgba(26,20,26,.92);border:1px solid ${C.selected};border-radius:9px;padding:7px 12px;color:#fff;font:600 11px/1 system-ui,sans-serif;letter-spacing:.06em;white-space:nowrap;box-shadow:0 0 18px rgba(33,150,243,.45),0 6px 16px rgba(0,0,0,.5);backdrop-filter:blur(4px)">${asset.name}</div>
          <div style="width:0;height:26px;border-left:1px dashed rgba(255,255,255,.55)"></div>
          <div style="width:9px;height:9px;border-radius:50%;background:#fff;box-shadow:0 0 0 4px rgba(33,150,243,.35)"></div>
        </div>
      `
      markersRef.current.push(new maplibregl.Marker({ element: el, anchor: 'bottom' }).setLngLat(asset.center).addTo(map))
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
        ::-webkit-scrollbar { width: 6px !important; height: 6px !important; }
        ::-webkit-scrollbar-button { display: none !important; height: 0 !important; width: 0 !important; }
        ::-webkit-scrollbar-thumb { background: #3e333d !important; border-radius: 4px !important; }
        ::-webkit-scrollbar-thumb:hover { background: #5a4f59 !important; }
        ::-webkit-scrollbar-track { background: transparent !important; }
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
        <main style={{ position: 'relative', flex: 1 }} onMouseMove={pokeHint}>
          <div ref={mapContainer} style={{ position: 'absolute', inset: 0 }} />
          {REALISTIC && <div style={{ position: 'absolute', inset: 0, zIndex: 0, pointerEvents: 'none', background: 'radial-gradient(ellipse at center, transparent 55%, rgba(20,14,19,.55) 100%)' }} />}
          <div style={{
            position: 'absolute', left: 20, top: 20, zIndex: 2,
            display: 'flex', alignItems: 'center', gap: 9,
            padding: '9px 14px', borderRadius: 999,
            background: 'rgba(31,24,30,.92)', border: `1px solid ${C.line}`,
            backdropFilter: 'blur(6px)', pointerEvents: 'none',
            fontSize: 12, color: '#cfc6cd', whiteSpace: 'nowrap',
            opacity: hint && selectedIds.length < 2 ? 1 : 0,
            transform: hint && selectedIds.length < 2 ? 'translateY(0)' : 'translateY(-6px)',
            transition: 'opacity .35s ease, transform .35s ease',
          }}>
            <kbd style={{ ...mono, fontSize: 10.5, padding: '3px 7px', borderRadius: 4, background: '#2b212a', border: `1px solid ${C.line}`, color: '#fff' }}>Ctrl</kbd>
            <span style={{ color: C.faint }}>+ click to select multiple assets</span>
          </div>
          <MapLegend preview={previewing} />
          <MapControls bearing={bearing} tilted={tilted} onZoom={(d) => mapRef.current?.easeTo({ zoom: (mapRef.current.getZoom() ?? 14) + d })} onCompass={() => mapRef.current?.easeTo({ bearing: 0, pitch: 55 })} onTilt={() => mapRef.current?.easeTo({ pitch: mapRef.current.getPitch() > 10 ? 0 : 58 })} />
        </main>

        <aside style={{ width: 440, flex: 'none', padding: 22, overflowY: 'auto', overflowX: 'hidden', background: C.panel, borderLeft: `1px solid ${C.line}` }}>
          {showHistory ? (
            <HistoryPanel 
              history={history} 
              onClose={() => setShowHistory(false)}
              onUpdateStatus={updateHistoryStatus}
              onPreview={(id) => { 
                setActiveRunId(id); 
                setShowHistory(false);
                const item = history.find(h => h.id === id);
                if (item) setSelectedIds(item.result.assets_analysis.map(a => a.asset_id));
              }}
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
              history={history}
            />
          ) : (
            <DeadspaceList assets={assets} onPick={(a) => selectOnly(a.id)} />
          )}
        </aside>
      </div>
    </div>
  )
}