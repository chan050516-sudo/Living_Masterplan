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

// Buildings
const BASE_SHADE = 0.38
const TOP_SHADE = 1.0
const SHADOW_OPACITY = 0.5
const ROOF_SHADE = 1.18
const EDGE_COLOUR = '#140e13'
const EDGE_OPACITY = 0.45

// Towers (glass curtain wall)
const TOWER_MIN_H = 25   // metres; taller than this gets the glass facade
const FIN_SPACING = 1.6  // metres between vertical fins
const FLOOR_H = 3.5      // metres per floor (slab lines)

// Parks
const GRASS = '#355e3b'
const M2_PER_TREE = 150
const MAX_TREES_PER_PARK = 400
const MAX_TREES = 8000

// Water
const WATER = '#0d5560'

type Cached = { id: string; status: string; tall: boolean; geos: THREE.BufferGeometry[] }

// Dusk gradient that water and glass reflect, matching the map sky.
function makeSkyEnv() {
  const c = document.createElement('canvas')
  c.width = 16; c.height = 256
  const g = c.getContext('2d')!
  const grad = g.createLinearGradient(0, 0, 0, 256)
  grad.addColorStop(0, '#1c141b')
  grad.addColorStop(0.48, '#6b4652')
  grad.addColorStop(0.52, '#4a3442')
  grad.addColorStop(1, '#2b212a')
  g.fillStyle = grad
  g.fillRect(0, 0, 16, 256)
  const t = new THREE.CanvasTexture(c)
  t.mapping = THREE.EquirectangularReflectionMapping
  t.colorSpace = THREE.SRGBColorSpace
  return t
}

function pointInRing(x: number, y: number, ring: THREE.Vector2[]): boolean {
  let inside = false
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const a = ring[i], b = ring[j]
    if ((a.y > y) !== (b.y > y) && x < ((b.x - a.x) * (y - a.y)) / (b.y - a.y) + a.x) inside = !inside
  }
  return inside
}

function disposeGroup(group: THREE.Group) {
  for (const child of group.children) {
    const mesh = child as THREE.Mesh
    mesh.geometry.dispose()
    const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material]
    mats.forEach((m) => m.dispose())
  }
  group.clear()
}

// Glass curtain wall drawn in the shader. Walls only; roofs keep the normal look.
// facadeUv is in metres: x along the wall, y up the wall.
function makeTowerMaterial(colour: string, env: THREE.Texture): THREE.MeshStandardMaterial {
  const mat = new THREE.MeshStandardMaterial({
    color: colour,
    vertexColors: true,
    roughness: 0.65,
    metalness: 0.1,
    envMap: env,
    envMapIntensity: 0.9,
  })
  mat.onBeforeCompile = (shader) => {
    shader.vertexShader = shader.vertexShader
      .replace('#include <common>', `#include <common>
        attribute vec2 facadeUv;
        varying vec2 vFacadeUv;
        varying float vFacadeUp;`)
      .replace('#include <begin_vertex>', `#include <begin_vertex>
        vFacadeUv = facadeUv;
        vFacadeUp = normal.y;`)

    shader.fragmentShader = shader.fragmentShader
      .replace('#include <common>', `#include <common>
        varying vec2 vFacadeUv;
        varying float vFacadeUp;
        // 1.0 on fins and floor slabs, 0.0 on glass.
        float facadeFrame() {
          float b = fract(vFacadeUv.x / ${FIN_SPACING.toFixed(2)});
          float fin = 1.0 - smoothstep(0.0, 0.07, b) * (1.0 - smoothstep(0.93, 1.0, b));
          float f = fract(vFacadeUv.y / ${FLOOR_H.toFixed(2)});
          float slab = 1.0 - smoothstep(0.0, 0.05, f);
          return max(fin, slab);
        }`)
      .replace('#include <color_fragment>', `#include <color_fragment>
        float fWall = step(vFacadeUp, 0.5);
        float fFrame = facadeFrame();
        vec3 glass = diffuseColor.rgb * 0.5;
        vec3 frame = diffuseColor.rgb * 1.15;
        diffuseColor.rgb = mix(diffuseColor.rgb, mix(glass, frame, fFrame), fWall);`)
      .replace('#include <roughnessmap_fragment>', `#include <roughnessmap_fragment>
        roughnessFactor = mix(roughnessFactor, mix(0.12, 0.6, fFrame), fWall);`)
      .replace('#include <metalnessmap_fragment>', `#include <metalnessmap_fragment>
        metalnessFactor = mix(metalnessFactor, mix(0.6, 0.1, fFrame), fWall);`)
  }
  mat.customProgramCacheKey = () => 'tower-facade'
  return mat
}

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
  const parks = new THREE.Group()
  const water = new THREE.Group()
  const edges = new THREE.Group()
  scene.add(buildings, parks, water, edges)

  const skyEnv = makeSkyEnv()

  // Lighting: cool sky fill + warm sun that casts shadows.
  scene.add(new THREE.HemisphereLight('#b9c6e6', '#2b212a', 0.9))
  const sun = new THREE.DirectionalLight('#fff1e0', 1.6)
  sun.castShadow = true
  sun.shadow.mapSize.set(4096, 4096)
  sun.shadow.bias = -0.0005
  sun.shadow.normalBias = 0.5
  scene.add(sun)
  scene.add(sun.target)

  // Invisible ground that only shows shadows.
  const ground = new THREE.Mesh(
    new THREE.PlaneGeometry(1, 1).rotateX(-Math.PI / 2),
    new THREE.ShadowMaterial({ opacity: SHADOW_OPACITY, depthWrite: false }),
  )
  ground.receiveShadow = true
  ground.position.y = 0.05
  scene.add(ground)

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

  function shapeOf(rings: Position[][]): THREE.Shape | null {
    if (!rings[0] || rings[0].length < 4) return null
    const shape = new THREE.Shape(ringToPoints(rings[0]))
    for (const hole of rings.slice(1)) shape.holes.push(new THREE.Path(ringToPoints(hole)))
    return shape
  }

  function polysOf(g: any): Position[][][] {
    return g?.type === 'Polygon' ? [g.coordinates] : g?.type === 'MultiPolygon' ? g.coordinates : []
  }

  // Flat surface lying on the ground at height y.
  function flatGeometry(shape: THREE.Shape, y: number): THREE.BufferGeometry {
    const geo = new THREE.ShapeGeometry(shape)
    geo.rotateX(-Math.PI / 2)
    geo.translate(0, y, 0)
    return geo
  }

  // ---------- Buildings ----------

  function addHeightGradient(geo: THREE.BufferGeometry, height: number) {
    geo.computeVertexNormals()
    const pos = geo.getAttribute('position')
    const nrm = geo.getAttribute('normal')
    const colors = new Float32Array(pos.count * 3)
    for (let i = 0; i < pos.count; i++) {
      // Roof faces point straight up: give them a brighter, sunlit shade.
      const isRoof = nrm.getY(i) > 0.9
      const t = Math.min(1, Math.max(0, pos.getY(i) / height))
      const s = isRoof ? ROOF_SHADE : BASE_SHADE + (TOP_SHADE - BASE_SHADE) * Math.pow(t, 0.7)
      colors[i * 3] = colors[i * 3 + 1] = colors[i * 3 + 2] = s
    }
    geo.setAttribute('color', new THREE.BufferAttribute(colors, 3))
  }

  function buildingGeometry(rings: Position[][], height: number): THREE.BufferGeometry | null {
    const shape = shapeOf(rings)
    if (!shape) return null
    const geo = new THREE.ExtrudeGeometry(shape, { depth: height, bevelEnabled: false })
    // Extrude's wall UVs are already in metres (along wall, up wall): keep a copy for the facade shader.
    geo.setAttribute('facadeUv', geo.getAttribute('uv').clone())
    geo.rotateX(-Math.PI / 2)
    geo.clearGroups()
    addHeightGradient(geo, height)
    return geo
  }

  function rebuild() {
    disposeGroup(buildings)
    const groups: Record<string, THREE.BufferGeometry[]> = {}
    for (const c of cache) {
      const key = selected.has(c.id) ? '__selected' : c.status + (c.tall ? '|tower' : '')
      ;(groups[key] ??= []).push(...c.geos)
    }

    for (const [key, geos] of Object.entries(groups)) {
      const merged = mergeGeometries(geos)
      if (!merged) continue
      const isSel = key === '__selected'
      const isTower = key.endsWith('|tower')
      const status = key.replace('|tower', '')
      const colour = isSel ? selectedColour : (STATUS_HEX[status] ?? STATUS_FALLBACK)
      const mat = isTower
        ? makeTowerMaterial(colour, skyEnv)
        : new THREE.MeshStandardMaterial({
            color: colour,
            vertexColors: true,
            roughness: 0.65,
            metalness: 0.1,
            emissive: isSel ? colour : '#000000',
            emissiveIntensity: isSel ? 0.35 : 0,
          })
      const mesh = new THREE.Mesh(merged, mat)
      mesh.castShadow = true
      mesh.receiveShadow = true
      buildings.add(mesh)
    }
    map?.triggerRepaint()
  }

  function fitShadows() {
    const box = new THREE.Box3().setFromObject(buildings)
    if (box.isEmpty()) return
    const centre = box.getCenter(new THREE.Vector3())
    const size = box.getSize(new THREE.Vector3())
    const r = Math.max(size.x, size.z) * 0.6 + 100

    sun.target.position.set(centre.x, 0, centre.z)
    sun.position.set(centre.x - 400, 600, centre.z + 300)
    const cam = sun.shadow.camera as THREE.OrthographicCamera
    cam.left = -r; cam.right = r; cam.top = r; cam.bottom = -r
    cam.near = 1; cam.far = 2000
    cam.updateProjectionMatrix()

    ground.position.set(centre.x, 0.05, centre.z)
    ground.scale.set(r * 2, 1, r * 2)
  }

  function setBuildings(fc: FeatureCollection) {
    for (const c of cache) c.geos.forEach((g) => g.dispose())
    cache = []
    for (const f of fc.features) {
      const props = (f.properties ?? {}) as Record<string, unknown>
      const id = String(props.id ?? '')
      const status = String(props.status ?? '')
      const height = Number(props.height) > 0 ? Number(props.height) : 8
      const geos: THREE.BufferGeometry[] = []
      for (const rings of polysOf(f.geometry)) {
        const geo = buildingGeometry(rings, height)
        if (geo) geos.push(geo)
      }
      if (geos.length) cache.push({ id, status, tall: height > TOWER_MIN_H, geos })
    }
    rebuild()
    fitShadows()

    // Crisp outlines on building corners and roof edges, built once per data load.
    disposeGroup(edges)
    const edgeGeos = cache.flatMap((c) => c.geos.map((g) => new THREE.EdgesGeometry(g, 30)))
    if (edgeGeos.length) {
      const merged = mergeGeometries(edgeGeos)
      edgeGeos.forEach((g) => g.dispose())
      if (merged) {
        edges.add(new THREE.LineSegments(merged, new THREE.LineBasicMaterial({
          color: EDGE_COLOUR, transparent: true, opacity: EDGE_OPACITY,
        })))
      }
    }
  }

  function setSelection(ids: string[], colour: string) {
    selected = new Set(ids)
    selectedColour = colour
    rebuild()
  }

  // ---------- Parks: grass + instanced trees ----------

  function setParks(fc: FeatureCollection) {
    disposeGroup(parks)
    const grassGeos: THREE.BufferGeometry[] = []
    const spots: Array<{ x: number; z: number; h: number }> = []

    for (const f of fc.features) {
      const id = String((f.properties as any)?.id ?? '')
      if (!id.startsWith('G-')) continue
      for (const rings of polysOf(f.geometry)) {
        const shape = shapeOf(rings)
        if (!shape) continue
        grassGeos.push(flatGeometry(shape, 0.3))

        // Scatter trees inside the outer ring, avoiding holes.
        const outer = ringToPoints(rings[0])
        const holes = rings.slice(1).map(ringToPoints)
        const area = Math.abs(THREE.ShapeUtils.area(outer))
        const want = Math.min(MAX_TREES_PER_PARK, Math.floor(area / M2_PER_TREE))
        let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity
        for (const p of outer) { minX = Math.min(minX, p.x); maxX = Math.max(maxX, p.x); minY = Math.min(minY, p.y); maxY = Math.max(maxY, p.y) }
        let placed = 0
        for (let tries = 0; placed < want && tries < want * 4; tries++) {
          const x = minX + Math.random() * (maxX - minX)
          const y = minY + Math.random() * (maxY - minY)
          if (!pointInRing(x, y, outer) || holes.some((h) => pointInRing(x, y, h))) continue
          spots.push({ x, z: -y, h: 5 + Math.random() * 6 })
          placed++
        }
      }
    }

    if (grassGeos.length) {
      const merged = mergeGeometries(grassGeos)
      grassGeos.forEach((g) => g.dispose())
      if (merged) {
        const grass = new THREE.Mesh(merged, new THREE.MeshStandardMaterial({ color: GRASS, roughness: 1 }))
        grass.receiveShadow = true
        parks.add(grass)
      }
    }

    const trees = spots.slice(0, MAX_TREES)
    if (trees.length) {
      const trunks = new THREE.InstancedMesh(
        new THREE.CylinderGeometry(0.25, 0.35, 1, 5),
        new THREE.MeshStandardMaterial({ color: '#4a3528', roughness: 1 }),
        trees.length,
      )
      const crowns = new THREE.InstancedMesh(
        new THREE.IcosahedronGeometry(1, 1),
        new THREE.MeshStandardMaterial({ color: '#ffffff', roughness: 0.9, flatShading: true }),
        trees.length,
      )
      const m = new THREE.Matrix4()
      const q = new THREE.Quaternion()
      const greens = ['#2f5d34', '#3b6e3a', '#2a5230', '#46783f']
      const col = new THREE.Color()
      trees.forEach((t, i) => {
        m.compose(new THREE.Vector3(t.x, 0.3 + t.h * 0.2, t.z), q, new THREE.Vector3(1, t.h * 0.4, 1))
        trunks.setMatrixAt(i, m)
        const r = t.h * 0.35
        m.compose(new THREE.Vector3(t.x, 0.3 + t.h * 0.62, t.z), q, new THREE.Vector3(r, r * 0.9, r))
        crowns.setMatrixAt(i, m)
        crowns.setColorAt(i, col.set(greens[i % greens.length]))
      })
      for (const tm of [trunks, crowns]) {
        tm.castShadow = true
        tm.receiveShadow = true
        parks.add(tm)
      }
    }
    map?.triggerRepaint()
  }

  // ---------- Water ----------

  function setWater(fc: FeatureCollection) {
    disposeGroup(water)
    const geos: THREE.BufferGeometry[] = []
    for (const f of fc.features) {
      for (const rings of polysOf(f.geometry)) {
        const shape = shapeOf(rings)
        if (shape) geos.push(flatGeometry(shape, 0.4))
      }
    }
    if (!geos.length) return
    const merged = mergeGeometries(geos)
    geos.forEach((g) => g.dispose())
    if (!merged) return
    const mesh = new THREE.Mesh(merged, new THREE.MeshStandardMaterial({
      color: WATER,
      roughness: 0.12,
      metalness: 0.0,
      envMap: skyEnv,
      envMapIntensity: 1.5,
      emissive: WATER,
      emissiveIntensity: 0.25,
      side: THREE.DoubleSide,
    }))
    mesh.receiveShadow = true
    water.add(mesh)
    map?.triggerRepaint()
  }

  const layer: maplibregl.CustomLayerInterface = {
    id: 'three-buildings',
    type: 'custom',
    renderingMode: '3d',

    onAdd(m: maplibregl.Map, gl: WebGLRenderingContext | WebGL2RenderingContext) {
      map = m
      renderer = new THREE.WebGLRenderer({ canvas: m.getCanvas(), context: gl, antialias: true })
      renderer.autoClear = false
      renderer.shadowMap.enabled = true
      renderer.shadowMap.type = THREE.PCFShadowMap

      // Water is static, so load it once here.
      fetch('/water.geojson')
        .then((r) => r.json())
        .then((fc: FeatureCollection) => setWater(fc))
        .catch(() => { /* no water file is fine */ })
    },

    render(gl: WebGLRenderingContext | WebGL2RenderingContext, args: any) {
      const matrix = args?.defaultProjectionData?.mainMatrix ?? args
      camera.projectionMatrix = new THREE.Matrix4().fromArray(matrix).multiply(local)
      renderer.resetState()
      renderer.setViewport(0, 0, gl.drawingBufferWidth, gl.drawingBufferHeight)
      renderer.render(scene, camera)
    },
  }

  return { layer, setBuildings, setSelection, setParks }
}