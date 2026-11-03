import * as THREE from 'three'
import * as maplibregl from 'maplibre-gl'
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
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

// Map filter: 'hide' removes non-matching assets, 'ghost' keeps them muted.
const FILTER_MODE = 'ghost' as 'hide' | 'ghost'
const GHOST_COLOUR = '#5c555e'
const GHOST_GRASS = '#3a3f3b'

// Towers (glass curtain wall)
const TOWER_MIN_H = 12
const FIN_SPACING = 1.6
const FLOOR_H = 3.5

// Building interventions
const GREEN_ROOF = '#4f7d3a'
const TIMBER = '#9a6a45'
const TIMBER_DARK = '#6e4a30'
const PLANTER = '#4c7a3d'
const SCAFFOLD = '#c9b48a'
const PAVING = '#b7aea3'
const LAMP_POLE = '#2a2628'
const LAMP_LIGHT = '#ffcf7a'

// Empty-land interventions (vacant parcels)
const NEW_DEV_H = 18            // metres, height of the proposed "ghost" building
const NEW_DEV_COLOUR = '#bfe9ff'
const FARM_MAX_PANELS = 1500
const HOLD_COLOUR = '#f2a900'

const PANEL_MODEL_URL = '/models/solar_panel.glb'
const PANEL_LENGTH = 4.0
const ROW_GAP = 1.2
const COL_GAP = 0.3
const SETBACK = 1.2
const MAX_PANELS = 300

// Cooling halo: ground glow sized by temperature reduction (deltaT, negative = cooler).
// No halo when deltaT is zero or positive (no cooling).
const HALO_COLOUR = '#6ee7d8'
const HALO_BASE_R = 60
const HALO_R_PER_DEG = 70
const HALO_STRENGTH = 1.0
// Placeholder cooling per type, used only when the analysis result has no real value.
const FAKE_DELTA_T: Record<string, number> = {
  green_corridor: -1.8,
  pedestrian_upgrade: -0.9,
  repurpose: -0.6,
  retrofit: -0.5,
  renovation: -0.3,
  interim_solar_farm: -0.4,
  new_development: 0,
  delay_development: 0,
}
const FAKE_DELTA_T_DEFAULT = -0.5

// Parks
const GRASS = '#355e3b'
const M2_PER_TREE = 150
const CROWN_M2 = 25
const MAX_TREES_PER_PARK = 400
const MAX_TREES = 6000

// Water
const WATER = '#0d5560'

type Cached = {
  id: string
  status: string
  tall: boolean
  height: number
  polys: Position[][][]
  geos: THREE.BufferGeometry[]
  edgeGeos: THREE.BufferGeometry[]
}

type Box = { x: number; y: number; z: number; sx: number; sy: number; sz: number; yaw: number }
type TreeSpot = { x: number; z: number; h: number }

export type HeroIntervention = { id: string; type: string; deltaT?: number }

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
  group.traverse((o) => {
    const m = o as THREE.Mesh
    if (m.geometry) m.geometry.dispose()
    if (m.material) (Array.isArray(m.material) ? m.material : [m.material]).forEach((x) => x.dispose())
  })
  group.clear()
}

function boxMesh(list: Box[], material: THREE.Material): THREE.InstancedMesh | null {
  if (!list.length) return null
  const inst = new THREE.InstancedMesh(new THREE.BoxGeometry(1, 1, 1), material, list.length)
  const m = new THREE.Matrix4()
  const q = new THREE.Quaternion()
  const up = new THREE.Vector3(0, 1, 0)
  list.forEach((b, i) => {
    q.setFromAxisAngle(up, b.yaw)
    m.compose(new THREE.Vector3(b.x, b.y, b.z), q, new THREE.Vector3(b.sx, b.sy, b.sz))
    inst.setMatrixAt(i, m)
  })
  inst.castShadow = true
  inst.receiveShadow = true
  return inst
}

function treeMeshes(spots: TreeSpot[], baseY: number): THREE.InstancedMesh[] {
  if (!spots.length) return []
  const trunks = new THREE.InstancedMesh(
    new THREE.CylinderGeometry(0.25, 0.35, 1, 5),
    new THREE.MeshStandardMaterial({ color: '#4a3528', roughness: 1 }),
    spots.length,
  )
  const crowns = new THREE.InstancedMesh(
    new THREE.IcosahedronGeometry(1, 0),
    new THREE.MeshStandardMaterial({ color: '#ffffff', roughness: 0.9, flatShading: true }),
    spots.length,
  )
  const m = new THREE.Matrix4()
  const q = new THREE.Quaternion()
  const greens = ['#2f5d34', '#3b6e3a', '#2a5230', '#46783f']
  const col = new THREE.Color()
  spots.forEach((t, i) => {
    m.compose(new THREE.Vector3(t.x, baseY + t.h * 0.2, t.z), q, new THREE.Vector3(1, t.h * 0.4, 1))
    trunks.setMatrixAt(i, m)
    const r = t.h * 0.35
    m.compose(new THREE.Vector3(t.x, baseY + t.h * 0.62, t.z), q, new THREE.Vector3(r, r * 0.9, r))
    crowns.setMatrixAt(i, m)
    crowns.setColorAt(i, col.set(greens[i % greens.length]))
  })
  trunks.castShadow = false
  crowns.castShadow = true
  trunks.receiveShadow = false
  crowns.receiveShadow = false
  return [trunks, crowns]
}

function frameOf(outer: THREE.Vector2[]) {
  let theta = 0, best = 0
  for (let i = 0; i < outer.length; i++) {
    const a = outer[i], b = outer[(i + 1) % outer.length]
    const len = a.distanceTo(b)
    if (len > best) { best = len; theta = Math.atan2(b.y - a.y, b.x - a.x) }
  }
  const cos = Math.cos(theta), sin = Math.sin(theta)
  let minU = Infinity, maxU = -Infinity, minV = Infinity, maxV = -Infinity
  for (const p of outer) {
    const u = p.x * cos + p.y * sin, v = -p.x * sin + p.y * cos
    minU = Math.min(minU, u); maxU = Math.max(maxU, u); minV = Math.min(minV, v); maxV = Math.max(maxV, v)
  }
  return {
    theta, minU, maxU, minV, maxV,
    toX: (u: number, v: number) => u * cos - v * sin,
    toY: (u: number, v: number) => u * sin + v * cos,
  }
}

function ringOutward(outer: THREE.Vector2[], offset: number, spacing: number) {
  const ccw = THREE.ShapeUtils.area(outer) > 0
  const out: Array<{ x: number; y: number; dir: THREE.Vector2; len: number; a: THREE.Vector2; n: THREE.Vector2 }> = []
  for (let i = 0; i < outer.length; i++) {
    const a = outer[i], b = outer[(i + 1) % outer.length]
    const len = a.distanceTo(b)
    if (len < 0.5) continue
    const dir = b.clone().sub(a).divideScalar(len)
    const n = ccw ? new THREE.Vector2(dir.y, -dir.x) : new THREE.Vector2(-dir.y, dir.x)
    const steps = Math.max(1, Math.round(len / spacing))
    for (let k = 0; k <= steps; k++) {
      const p = a.clone().addScaledVector(dir, (len * k) / steps).addScaledVector(n, offset)
      out.push({ x: p.x, y: p.y, dir, len, a, n })
    }
  }
  return out
}

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

function makeHaloMaterial(time: { value: number }, phase: number): THREE.ShaderMaterial {
  return new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    uniforms: {
      uColor: { value: new THREE.Color(HALO_COLOUR) },
      uTime: time,
      uPhase: { value: phase },
      uStrength: { value: HALO_STRENGTH },
    },
    vertexShader: `
      varying vec2 vUv;
      void main() {
        vUv = uv;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }`,
    fragmentShader: `
      uniform vec3 uColor;
      uniform float uTime;
      uniform float uPhase;
      uniform float uStrength;
      varying vec2 vUv;
      void main() {
        float d = length(vUv - 0.5) * 2.0;
        if (d > 1.0) discard;
        float base = pow(1.0 - d, 1.6) * 0.32;
        float w = fract(d - uTime * 0.22 + uPhase);
        float ring = smoothstep(0.0, 0.06, w) * (1.0 - smoothstep(0.06, 0.18, w)) * (1.0 - d) * 0.45;
        gl_FragColor = vec4(uColor, (base + ring) * uStrength);
      }`,
  })
}

// Diagonal amber stripes for "on hold" parcels. Uses ground position, so stripes stay a fixed size.
function makeHatchMaterial(): THREE.ShaderMaterial {
  return new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    uniforms: { uColor: { value: new THREE.Color(HOLD_COLOUR) } },
    vertexShader: `
      varying vec2 vPos;
      void main() {
        vPos = position.xz;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }`,
    fragmentShader: `
      uniform vec3 uColor;
      varying vec2 vPos;
      void main() {
        float s = step(0.5, fract((vPos.x + vPos.y) / 6.0));
        gl_FragColor = vec4(uColor, mix(0.08, 0.42, s));
      }`,
  })
}

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
  const hero = new THREE.Group()
  const halos = new THREE.Group()
  scene.add(buildings, parks, water, edges, hero, halos)

  const skyEnv = makeSkyEnv()
  const gltfLoader = new GLTFLoader()
  const haloTime = { value: 0 }

  let shadowDirty = true
  function redraw() {
    shadowDirty = true
    map?.triggerRepaint()
  }

  type PanelPart = { geometry: THREE.BufferGeometry; material: THREE.Material | THREE.Material[]; matrix: THREE.Matrix4 }
  let panelParts: PanelPart[] | null = null
  let panelSize = { w: PANEL_LENGTH, d: 1.0 }

  function loadPanelTemplate() {
    gltfLoader.load(PANEL_MODEL_URL, (gltf) => {
      const root = gltf.scene
      root.updateMatrixWorld(true)
      const box = new THREE.Box3().setFromObject(root)
      const size = box.getSize(new THREE.Vector3())
      const centre = box.getCenter(new THREE.Vector3())
      const turn = size.z > size.x
      const long = Math.max(size.x, size.z)
      const short = Math.min(size.x, size.z)
      const s = PANEL_LENGTH / long

      const norm = new THREE.Matrix4().makeScale(s, s, s)
        .multiply(new THREE.Matrix4().makeRotationY(turn ? Math.PI / 2 : 0))
        .multiply(new THREE.Matrix4().makeTranslation(-centre.x, -box.min.y, -centre.z))

      const parts: PanelPart[] = []
      root.traverse((o) => {
        const m = o as THREE.Mesh
        if (!m.isMesh) return
        const mats = Array.isArray(m.material) ? m.material : [m.material]
        mats.forEach((mat) => {
          if ((mat as THREE.MeshStandardMaterial).isMeshStandardMaterial) {
            ;(mat as THREE.MeshStandardMaterial).envMap = skyEnv
            ;(mat as THREE.MeshStandardMaterial).envMapIntensity = 1.2
          }
        })
        parts.push({ geometry: m.geometry, material: m.material, matrix: norm.clone().multiply(m.matrixWorld) })
      })
      panelParts = parts
      panelSize = { w: PANEL_LENGTH, d: short * s }
      updateHero()
    }, undefined, (err) => console.warn('[three] solar panel model failed to load', err))
  }

  scene.add(new THREE.HemisphereLight('#b9c6e6', '#2b212a', 0.9))
  const sun = new THREE.DirectionalLight('#fff1e0', 1.6)
  sun.castShadow = true
  sun.shadow.mapSize.set(4096, 4096)
  sun.shadow.bias = -0.0005
  sun.shadow.normalBias = 0.5
  scene.add(sun)
  scene.add(sun.target)

  const ground = new THREE.Mesh(
    new THREE.PlaneGeometry(1, 1).rotateX(-Math.PI / 2),
    new THREE.ShadowMaterial({ opacity: SHADOW_OPACITY, depthWrite: false }),
  )
  ground.receiveShadow = true
  ground.position.y = 0.05
  scene.add(ground)

  let cache: Cached[] = []
  let areaPolys = new Map<string, Position[][][]>() // every flat area (parks, vacant parcels) by id
  let selected = new Set<string>()
  let selectedColour = '#2196f3'
  let heroes = new Map<string, string>()
  let deltas = new Map<string, number>()
  let visibleIds: Set<string> | null = null
  let lastParks: FeatureCollection | null = null

  const isShown = (id: string) => !visibleIds || visibleIds.has(id) || selected.has(id) || heroes.has(id)

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

  function flatGeometry(shape: THREE.Shape, y: number): THREE.BufferGeometry {
    const geo = new THREE.ShapeGeometry(shape)
    geo.rotateX(-Math.PI / 2)
    geo.translate(0, y, 0)
    return geo
  }

  function centreOfPolys(polys: Position[][][]): THREE.Vector3 {
    let minX = Infinity, maxX = -Infinity, minZ = Infinity, maxZ = -Infinity
    for (const rings of polys) for (const p of ringToPoints(rings[0])) {
      minX = Math.min(minX, p.x); maxX = Math.max(maxX, p.x)
      minZ = Math.min(minZ, -p.y); maxZ = Math.max(maxZ, -p.y)
    }
    return new THREE.Vector3((minX + maxX) / 2, 0, (minZ + maxZ) / 2)
  }

  // ---------- Buildings ----------

  function addHeightGradient(geo: THREE.BufferGeometry, height: number) {
    geo.computeVertexNormals()
    const pos = geo.getAttribute('position')
    const nrm = geo.getAttribute('normal')
    const colors = new Float32Array(pos.count * 3)
    for (let i = 0; i < pos.count; i++) {
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
      if (heroes.has(c.id)) continue
      let key: string
      if (!isShown(c.id)) {
        if (FILTER_MODE === 'hide') continue
        key = '__ghost'
      } else {
        key = selected.has(c.id) ? '__selected' : c.status + (c.tall ? '|tower' : '')
      }
      ;(groups[key] ??= []).push(...c.geos)
    }

    for (const [key, geos] of Object.entries(groups)) {
      const merged = mergeGeometries(geos)
      if (!merged) continue

      if (key === '__ghost') {
        const ghost = new THREE.Mesh(merged, new THREE.MeshStandardMaterial({
          color: GHOST_COLOUR, vertexColors: true, roughness: 0.9,
        }))
        ghost.castShadow = true
        ghost.receiveShadow = true
        buildings.add(ghost)
        continue
      }

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
    redraw()
  }

  function rebuildEdges() {
    disposeGroup(edges)
    const geos = cache.filter((c) => isShown(c.id)).flatMap((c) => c.edgeGeos)
    if (!geos.length) return
    const merged = mergeGeometries(geos)
    if (merged) {
      edges.add(new THREE.LineSegments(merged, new THREE.LineBasicMaterial({
        color: EDGE_COLOUR, transparent: true, opacity: EDGE_OPACITY,
      })))
    }
    redraw()
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
    redraw()
  }

  // ---------- Intervention upgrades ----------

  // Solar rows along the longest edge. Used for retrofit (roof) and interim solar farm (ground).
  function addSolar(outer: THREE.Vector2[], baseY: number, maxPanels = MAX_PANELS) {
    if (!panelParts) return
    const f = frameOf(outer)
    const hw = panelSize.w / 2, hd = panelSize.d / 2
    const m = SETBACK
    const spots: Array<{ x: number; z: number }> = []
    for (let u = f.minU + m + hw; u <= f.maxU - m - hw; u += panelSize.w + COL_GAP) {
      for (let v = f.minV + m + hd; v <= f.maxV - m - hd; v += panelSize.d + ROW_GAP) {
        const corners = [[-hw - m, -hd - m], [hw + m, -hd - m], [-hw - m, hd + m], [hw + m, hd + m], [0, 0]]
        const inside = corners.every(([du, dv]) => pointInRing(f.toX(u + du, v + dv), f.toY(u + du, v + dv), outer))
        if (inside) spots.push({ x: f.toX(u, v), z: -f.toY(u, v) })
      }
    }
    const placed = spots.slice(0, maxPanels)
    if (!placed.length) return

    const pm = new THREE.Matrix4()
    const q = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), f.theta)
    const one = new THREE.Vector3(1, 1, 1)
    for (const part of panelParts) {
      const mat = Array.isArray(part.material) ? part.material.map((x) => x.clone()) : part.material.clone()
      const inst = new THREE.InstancedMesh(part.geometry.clone(), mat, placed.length)
      placed.forEach((s, i) => {
        pm.compose(new THREE.Vector3(s.x, baseY, s.z), q, one).multiply(part.matrix)
        inst.setMatrixAt(i, pm)
      })
      inst.castShadow = true
      inst.receiveShadow = true
      hero.add(inst)
    }
  }

  function addScaffold(outer: THREE.Vector2[], height: number) {
    const top = height + 1
    const poles: Box[] = []
    const ledgers: Box[] = []
    const seen = new Set<string>()
    for (const p of ringOutward(outer, 1.2, 2.5)) {
      poles.push({ x: p.x, y: top / 2, z: -p.y, sx: 0.12, sy: top, sz: 0.12, yaw: 0 })
      const key = `${p.a.x},${p.a.y}`
      if (seen.has(key)) continue
      seen.add(key)
      const mid = p.a.clone().addScaledVector(p.dir, p.len / 2).addScaledVector(p.n, 1.2)
      const yaw = Math.atan2(p.dir.y, p.dir.x)
      for (let h = 2; h <= top; h += 2) {
        ledgers.push({ x: mid.x, y: h, z: -mid.y, sx: p.len, sy: 0.08, sz: 0.08, yaw })
      }
    }
    const mat = new THREE.MeshStandardMaterial({ color: SCAFFOLD, roughness: 0.5, metalness: 0.6 })
    for (const mesh of [boxMesh(poles, mat), boxMesh(ledgers, mat.clone())]) if (mesh) hero.add(mesh)
  }

  function addTerrace(shape: THREE.Shape, outer: THREE.Vector2[], roofY: number) {
    const deck = new THREE.Mesh(flatGeometry(shape, roofY + 0.05), new THREE.MeshStandardMaterial({ color: TIMBER, roughness: 0.85 }))
    deck.receiveShadow = true
    hero.add(deck)

    const f = frameOf(outer)
    const GRID = 4, M = 1.0, POST_H = 2.6
    const us: number[] = [], vs: number[] = []
    for (let u = f.minU + M; u <= f.maxU - M; u += GRID) us.push(u)
    for (let v = f.minV + M; v <= f.maxV - M; v += GRID) vs.push(v)
    const ok = us.map((u) => vs.map((v) => pointInRing(f.toX(u, v), f.toY(u, v), outer)))

    const posts: Box[] = [], beams: Box[] = [], planters: Box[] = []
    const beamY = roofY + POST_H
    for (let i = 0; i < us.length; i++) {
      for (let j = 0; j < vs.length; j++) {
        if (!ok[i][j]) continue
        const u = us[i], v = vs[j]
        posts.push({ x: f.toX(u, v), y: roofY + POST_H / 2, z: -f.toY(u, v), sx: 0.2, sy: POST_H, sz: 0.2, yaw: 0 })
        if (i + 1 < us.length && ok[i + 1][j]) {
          const mu = u + GRID / 2
          beams.push({ x: f.toX(mu, v), y: beamY, z: -f.toY(mu, v), sx: GRID, sy: 0.18, sz: 0.14, yaw: f.theta })
        }
        if (j + 1 < vs.length && ok[i][j + 1]) {
          const mv = v + GRID / 2
          beams.push({ x: f.toX(u, mv), y: beamY, z: -f.toY(u, mv), sx: GRID, sy: 0.18, sz: 0.14, yaw: f.theta + Math.PI / 2 })
        }
        const cellOk = i + 1 < us.length && j + 1 < vs.length && ok[i + 1][j] && ok[i][j + 1] && ok[i + 1][j + 1]
        if (cellOk && (i + j) % 2 === 0) {
          const cu = u + GRID / 2, cv = v + GRID / 2
          planters.push({ x: f.toX(cu, cv), y: roofY + 0.35, z: -f.toY(cu, cv), sx: 1.4, sy: 0.6, sz: 0.7, yaw: f.theta })
        }
      }
    }
    const wood = new THREE.MeshStandardMaterial({ color: TIMBER_DARK, roughness: 0.8 })
    const green = new THREE.MeshStandardMaterial({ color: PLANTER, roughness: 0.95 })
    for (const mesh of [boxMesh(posts, wood), boxMesh(beams, wood.clone()), boxMesh(planters, green)]) if (mesh) hero.add(mesh)
  }

  function addGreenCorridor(shape: THREE.Shape, outer: THREE.Vector2[], roofY: number) {
    const roof = new THREE.Mesh(flatGeometry(shape, roofY), new THREE.MeshStandardMaterial({ color: GREEN_ROOF, roughness: 1 }))
    roof.receiveShadow = true
    hero.add(roof)
    const spots: TreeSpot[] = ringOutward(outer, 4.5, 8).map((p) => ({ x: p.x, z: -p.y, h: 6 + Math.random() * 4 }))
    treeMeshes(spots, 0.3).forEach((m) => hero.add(m))
  }

  function addForecourt(outer: THREE.Vector2[]) {
    const f = frameOf(outer)
    const PAD = 8
    const corners: Array<[number, number]> = [
      [f.minU - PAD, f.minV - PAD], [f.maxU + PAD, f.minV - PAD],
      [f.maxU + PAD, f.maxV + PAD], [f.minU - PAD, f.maxV + PAD],
    ]
    const pts = corners.map(([u, v]) => new THREE.Vector2(f.toX(u, v), f.toY(u, v)))
    const paving = new THREE.Mesh(flatGeometry(new THREE.Shape(pts), 0.35), new THREE.MeshStandardMaterial({ color: PAVING, roughness: 0.9 }))
    paving.receiveShadow = true
    hero.add(paving)

    const POLE_H = 4.5
    const poles: Box[] = [], heads: Box[] = []
    for (let i = 0; i < pts.length; i++) {
      const a = pts[i], b = pts[(i + 1) % pts.length]
      const len = a.distanceTo(b)
      const steps = Math.max(1, Math.round(len / 10))
      for (let k = 0; k < steps; k++) {
        const p = a.clone().lerp(b, k / steps)
        poles.push({ x: p.x, y: POLE_H / 2, z: -p.y, sx: 0.14, sy: POLE_H, sz: 0.14, yaw: 0 })
        heads.push({ x: p.x, y: POLE_H + 0.1, z: -p.y, sx: 0.5, sy: 0.15, sz: 0.5, yaw: f.theta })
      }
    }
    const poleMat = new THREE.MeshStandardMaterial({ color: LAMP_POLE, roughness: 0.6, metalness: 0.4 })
    const lightMat = new THREE.MeshStandardMaterial({ color: LAMP_LIGHT, emissive: LAMP_LIGHT, emissiveIntensity: 1.5 })
    for (const mesh of [boxMesh(poles, poleMat), boxMesh(heads, lightMat)]) if (mesh) hero.add(mesh)
  }

  // new_development: translucent glass massing with floor outlines, showing a proposed building.
  function addNewDevelopment(outer: THREE.Vector2[]) {
    const f = frameOf(outer)
    const w = (f.maxU - f.minU) * 0.6
    const d = (f.maxV - f.minV) * 0.6
    if (w < 2 || d < 2) return
    const cu = (f.minU + f.maxU) / 2, cv = (f.minV + f.maxV) / 2
    const pos = new THREE.Vector3(f.toX(cu, cv), NEW_DEV_H / 2 + 0.3, -f.toY(cu, cv))

    const geo = new THREE.BoxGeometry(w, NEW_DEV_H, d)
    const glass = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({
      color: NEW_DEV_COLOUR, transparent: true, opacity: 0.25,
      roughness: 0.1, metalness: 0.3, envMap: skyEnv, depthWrite: false,
    }))
    glass.position.copy(pos)
    glass.rotation.y = f.theta
    hero.add(glass)

    const lineMat = () => new THREE.LineBasicMaterial({ color: NEW_DEV_COLOUR, transparent: true, opacity: 0.85 })
    const outline = new THREE.LineSegments(new THREE.EdgesGeometry(geo), lineMat())
    outline.position.copy(pos)
    outline.rotation.y = f.theta
    hero.add(outline)

    for (let h = FLOOR_H; h < NEW_DEV_H; h += FLOOR_H) {
      const floor = new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(w, 0.01, d)), lineMat())
      floor.position.set(pos.x, 0.3 + h, pos.z)
      floor.rotation.y = f.theta
      ;(floor.material as THREE.LineBasicMaterial).opacity = 0.35
      hero.add(floor)
    }
  }

  // delay_development: amber hatched overlay with an amber border, reading as "on hold".
  function addHold(shape: THREE.Shape, outer: THREE.Vector2[]) {
    const hatch = new THREE.Mesh(flatGeometry(shape, 0.45), makeHatchMaterial())
    hatch.renderOrder = 1
    hero.add(hatch)
    const border = new THREE.LineLoop(
      new THREE.BufferGeometry().setFromPoints(outer.map((p) => new THREE.Vector3(p.x, 0.5, -p.y))),
      new THREE.LineBasicMaterial({ color: HOLD_COLOUR }),
    )
    hero.add(border)
  }

  function buildHero(c: Cached, type: string) {
    const isSel = selected.has(c.id)
    const colour = isSel ? selectedColour : (STATUS_HEX[c.status] ?? STATUS_FALLBACK)
    const body = mergeGeometries(c.geos)
    if (body) {
      const mesh = new THREE.Mesh(body, new THREE.MeshStandardMaterial({
        color: colour, vertexColors: true, roughness: 0.6, metalness: 0.1,
        emissive: isSel ? colour : '#000000', emissiveIntensity: isSel ? 0.2 : 0,
      }))
      mesh.castShadow = true
      mesh.receiveShadow = true
      hero.add(mesh)
    }

    const roofY = c.height + 0.15
    for (const rings of c.polys) {
      const shape = shapeOf(rings)
      if (!shape) continue
      const outer = ringToPoints(rings[0])
      switch (type) {
        case 'renovation': addScaffold(outer, c.height); break
        case 'repurpose': addTerrace(shape, outer, roofY); break
        case 'green_corridor': addGreenCorridor(shape, outer, roofY); break
        case 'pedestrian_upgrade': addForecourt(outer); break
        case 'retrofit':
        default: addSolar(outer, roofY)
      }
    }
  }

  // Interventions on empty land (vacant parcels), which have no building to modify.
  function buildParcelHero(polys: Position[][][], type: string) {
    for (const rings of polys) {
      const shape = shapeOf(rings)
      if (!shape) continue
      const outer = ringToPoints(rings[0])
      switch (type) {
        case 'interim_solar_farm': addSolar(outer, 0.3, FARM_MAX_PANELS); break
        case 'new_development': addNewDevelopment(outer); break
        case 'delay_development':
        default: addHold(shape, outer)
      }
    }
  }

  function buildHalo(id: string, type: string, centre: THREE.Vector3, index: number) {
    const dT = deltas.get(id) ?? FAKE_DELTA_T[type] ?? FAKE_DELTA_T_DEFAULT
    if (dT >= 0) return // no cooling, no halo
    const r = HALO_BASE_R + Math.abs(dT) * HALO_R_PER_DEG
    const disc = new THREE.Mesh(
      new THREE.PlaneGeometry(2, 2).rotateX(-Math.PI / 2),
      makeHaloMaterial(haloTime, index * 0.37),
    )
    disc.position.copy(centre).setY(0.6)
    disc.scale.set(r, 1, r)
    disc.renderOrder = 2
    halos.add(disc)
  }

  function updateHero() {
    disposeGroup(hero)
    disposeGroup(halos)
    let i = 0
    for (const [id, type] of heroes) {
      const c = cache.find((x) => x.id === id)
      let centre: THREE.Vector3
      if (c) {
        buildHero(c, type)
        centre = centreOfPolys(c.polys)
      } else {
        const polys = areaPolys.get(id)
        if (!polys) continue
        buildParcelHero(polys, type)
        centre = centreOfPolys(polys)
      }
      buildHalo(id, type, centre, i++)
    }
    redraw()
  }

  function setBuildings(fc: FeatureCollection) {
    for (const c of cache) {
      c.geos.forEach((g) => g.dispose())
      c.edgeGeos.forEach((g) => g.dispose())
    }
    cache = []
    for (const f of fc.features) {
      const props = (f.properties ?? {}) as Record<string, unknown>
      const id = String(props.id ?? '')
      const status = String(props.status ?? '')
      const height = Number(props.height) > 0 ? Number(props.height) : 8
      const polys = polysOf(f.geometry)
      const geos: THREE.BufferGeometry[] = []
      for (const rings of polys) {
        const geo = buildingGeometry(rings, height)
        if (geo) geos.push(geo)
      }
      if (geos.length) {
        const edgeGeos = geos.map((g) => new THREE.EdgesGeometry(g, 30))
        cache.push({ id, status, tall: height > TOWER_MIN_H, height, polys, geos, edgeGeos })
      }
    }
    rebuild()
    fitShadows()
    updateHero()
    rebuildEdges()
  }

  function setSelection(ids: string[], colour: string) {
    selected = new Set(ids)
    selectedColour = colour
    rebuild()
    updateHero()
  }

  function setInterventions(list: HeroIntervention[]) {
    const next = new Map(list.map((h) => [h.id, h.type]))
    const nextDeltas = new Map<string, number>()
    for (const h of list) if (typeof h.deltaT === 'number') nextDeltas.set(h.id, h.deltaT)
    const same =
      next.size === heroes.size && [...next].every(([k, v]) => heroes.get(k) === v) &&
      nextDeltas.size === deltas.size && [...nextDeltas].every(([k, v]) => deltas.get(k) === v)
    if (same) return
    heroes = next
    deltas = nextDeltas
    rebuild()
    updateHero()
  }

  function setFilter(ids: string[] | null) {
    const next = ids ? new Set(ids) : null
    const same =
      (next === null && visibleIds === null) ||
      (next !== null && visibleIds !== null && next.size === visibleIds.size && [...next].every((x) => visibleIds!.has(x)))
    if (same) return
    visibleIds = next
    rebuild()
    rebuildEdges()
    if (lastParks) setParks(lastParks)
  }

  // ---------- Areas: parks (grass + real canopy trees), plus remembering parcel shapes ----------

  function setParks(fc: FeatureCollection) {
    lastParks = fc
    disposeGroup(parks)

    // Remember every area's shape so empty-land interventions can be drawn on it.
    areaPolys = new Map()
    for (const f of fc.features) {
      const id = String((f.properties as any)?.id ?? '')
      if (id) areaPolys.set(id, polysOf(f.geometry))
    }

    const grassGeos: THREE.BufferGeometry[] = []
    const mutedGeos: THREE.BufferGeometry[] = []
    const spots: TreeSpot[] = []

    for (const f of fc.features) {
      const props = (f.properties ?? {}) as Record<string, unknown>
      const id = String(props.id ?? '')
      if (!id.startsWith('G-')) continue
      const muted = !isShown(id)
      if (muted && FILTER_MODE === 'hide') continue

      for (const rings of polysOf(f.geometry)) {
        const shape = shapeOf(rings)
        if (!shape) continue
        if (muted) { mutedGeos.push(flatGeometry(shape, 0.3)); continue }
        grassGeos.push(flatGeometry(shape, 0.3))

        const outer = ringToPoints(rings[0])
        const holes = rings.slice(1).map(ringToPoints)
        const area = Math.abs(THREE.ShapeUtils.area(outer))
        const rawCanopy = props.canopy
        const hasCanopy = rawCanopy != null && Number.isFinite(Number(rawCanopy))
        const want = Math.min(
          MAX_TREES_PER_PARK,
          Math.floor(hasCanopy ? (area * Number(rawCanopy)) / CROWN_M2 : area / M2_PER_TREE),
        )
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

    for (const [geos, colour] of [[grassGeos, GRASS], [mutedGeos, GHOST_GRASS]] as const) {
      if (!geos.length) continue
      const merged = mergeGeometries(geos)
      geos.forEach((g) => g.dispose())
      if (!merged) continue
      const grass = new THREE.Mesh(merged, new THREE.MeshStandardMaterial({ color: colour, roughness: 1 }))
      grass.receiveShadow = true
      parks.add(grass)
    }

    treeMeshes(spots.slice(0, MAX_TREES), 0.3).forEach((m) => parks.add(m))
    updateHero() // parcels are known now, so empty-land interventions can draw
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
    redraw()
  }

  const layer: maplibregl.CustomLayerInterface = {
    id: 'three-buildings',
    type: 'custom',
    renderingMode: '3d',

    onAdd(m: maplibregl.Map, gl: WebGLRenderingContext | WebGL2RenderingContext) {
      map = m
      loadPanelTemplate()
      renderer = new THREE.WebGLRenderer({ canvas: m.getCanvas(), context: gl, antialias: true })
      renderer.autoClear = false
      renderer.shadowMap.enabled = true
      renderer.shadowMap.type = THREE.PCFShadowMap
      renderer.shadowMap.autoUpdate = false

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
      if (shadowDirty) {
        renderer.shadowMap.needsUpdate = true
        shadowDirty = false
      }
      renderer.render(scene, camera)

      if (halos.children.length) {
        haloTime.value = performance.now() / 1000
        map?.triggerRepaint()
      }
    },
  }

  return { layer, setBuildings, setSelection, setParks, setInterventions, setFilter }
}