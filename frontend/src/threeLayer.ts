import * as THREE from 'three'
import * as maplibregl from 'maplibre-gl'
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js'
import type { FeatureCollection, Position } from 'geojson'

const STATUS_HEX: Record<string, string> = {
  healthy: '#3fb27f', monitor: '#f7931d', improvement_opportunity: '#f7931d',
  development_risk: '#f15c22', deadspace_candidate: '#d71920', underperforming_facility: '#d71920',
  intervened: '#00d2ff', vacant: '#9e9e9e',
}
const STATUS_FALLBACK = '#5a4f59'

type Cached = { id: string; status: string; geos: THREE.BufferGeometry[] }

// Three.js scene drawn inside MapLibre's own WebGL context.
// Scene units are metres from `origin`: X east, Y up, Z south.
export function createThreeLayer(origin: [number, number]) {
  const merc = maplibregl.MercatorCoordinate.fromLngLat(origin, 0)
  const scale = merc.meterInMercatorCoordinateUnits()

  const local = new THREE.Matrix4()
    .makeTranslation(merc.x, merc.y, merc.z)
    .scale(new THREE.Vector3(scale, -scale, scale))
    .multiply(new THREE.Matrix4().makeRotationX(Math.PI / 2))

  let map: maplibregl.Map | null = null
  let renderer: THREE.WebGLRenderer
  const scene = new THREE.Scene()
  const camera = new THREE.Camera()
  const buildings = new THREE.Group()
  scene.add(buildings)

  // Per-building geometry, built once per data load and reused on every selection change.
  let cache: Cached[] = []
  let selected = new Set<string>()
  let selectedColour = '#2196f3'

  function toShapePoint(p: Position): THREE.Vector2 {
    const m = maplibregl.MercatorCoordinate.fromLngLat([p[0], p[1]], 0)
    const x = (m.x - merc.x) / scale
    const z = (m.y - merc.y) / scale
    return new THREE.Vector2(x, -z)
  }

  function ringToPoints(ring: Position[]): THREE.Vector2[] {
    const pts = ring.map(toShapePoint)
    if (pts.length > 1 && pts[0].equals(pts[pts.length - 1])) pts.pop()
    return pts
  }

  function polygonToGeometry(rings: Position[][], height: number): THREE.BufferGeometry | null {
    if (!rings[0] || rings[0].length < 4) return null
    const shape = new THREE.Shape(ringToPoints(rings[0]))
    for (const hole of rings.slice(1)) shape.holes.push(new THREE.Path(ringToPoints(hole)))
    const geo = new THREE.ExtrudeGeometry(shape, { depth: height, bevelEnabled: false })
    geo.rotateX(-Math.PI / 2)
    return geo
  }

  function clearMeshes() {
    for (const child of buildings.children) {
      const mesh = child as THREE.Mesh
      mesh.geometry.dispose()
      ;(mesh.material as THREE.Material).dispose()
    }
    buildings.clear()
  }

  // Merge cached geometries into one mesh per group: each status, plus "selected".
  function rebuild() {
    clearMeshes()
    const groups: Record<string, THREE.BufferGeometry[]> = {}
    for (const c of cache) {
      const key = selected.has(c.id) ? '__selected' : c.status
      ;(groups[key] ??= []).push(...c.geos)
    }

    for (const [key, geos] of Object.entries(groups)) {
      const merged = mergeGeometries(geos)
      if (!merged) continue
      const isSel = key === '__selected'
      const colour = isSel ? selectedColour : (STATUS_HEX[key] ?? STATUS_FALLBACK)
      const mat = new THREE.MeshStandardMaterial({
        color: colour,
        roughness: 0.8,
        metalness: 0.05,
        emissive: isSel ? colour : '#000000',
        emissiveIntensity: isSel ? 0.35 : 0,
      })
      buildings.add(new THREE.Mesh(merged, mat))
    }
    map?.triggerRepaint()
  }

  function setBuildings(fc: FeatureCollection) {
    for (const c of cache) c.geos.forEach((g) => g.dispose())
    cache = []
    for (const f of fc.features) {
      const props = (f.properties ?? {}) as Record<string, unknown>
      const id = String(props.id ?? '')
      const status = String(props.status ?? '')
      const height = Number(props.height) > 0 ? Number(props.height) : 8
      const g = f.geometry
      const polys = g.type === 'Polygon' ? [g.coordinates] : g.type === 'MultiPolygon' ? g.coordinates : []
      const geos: THREE.BufferGeometry[] = []
      for (const rings of polys) {
        const geo = polygonToGeometry(rings, height)
        if (geo) geos.push(geo)
      }
      if (geos.length) cache.push({ id, status, geos })
    }
    rebuild()
  }

  function setSelection(ids: string[], colour: string) {
    selected = new Set(ids)
    selectedColour = colour
    rebuild()
  }

  const layer: maplibregl.CustomLayerInterface = {
    id: 'three-buildings',
    type: 'custom',
    renderingMode: '3d',

    onAdd(m: maplibregl.Map, gl: WebGLRenderingContext | WebGL2RenderingContext) {
      map = m
      scene.add(new THREE.AmbientLight(0xffffff, 0.55))
      const sun = new THREE.DirectionalLight(0xfff4ea, 1.3)
      sun.position.set(-150, 300, 120)
      scene.add(sun)

      renderer = new THREE.WebGLRenderer({ canvas: m.getCanvas(), context: gl, antialias: true })
      renderer.autoClear = false
    },

    render(_gl: unknown, args: any) {
      const matrix = args?.defaultProjectionData?.mainMatrix ?? args
      camera.projectionMatrix = new THREE.Matrix4().fromArray(matrix).multiply(local)
      renderer.resetState()
      renderer.render(scene, camera)
    },
  }

  return { layer, setBuildings, setSelection }
}