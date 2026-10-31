import * as THREE from 'three'
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js'
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js'
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js'

type Building = { p: number[]; h: number; s: number; t?: number }

export type Scene3D = { setStep: (step: number) => void; setScroll: (t: number) => void; setActive: (on: boolean) => void; dispose: () => void }

// One camera and colour state per story beat. -1 is the hero.
type Beat = { radius: number; polar: number; azimuth: number; focus: number; dead: number; fixed: number; shift: number; spin: number }
const BEATS: Record<number, Beat> = {
  [-1]: { radius: 3300, polar: 0.98, azimuth: 0.5, focus: 0, dead: 1, fixed: 0, shift: -0.2, spin: 0.05 },
  0: { radius: 3300, polar: 0.62, azimuth: 1.1, focus: 0, dead: 0, fixed: 0, shift: 0.2, spin: 0.02 },
  1: { radius: 2800, polar: 0.82, azimuth: 1.7, focus: 0, dead: 1, fixed: 0, shift: 0.2, spin: 0.02 },
  2: { radius: 950, polar: 1.0, azimuth: 2.3, focus: 1, dead: 0.35, fixed: 0, shift: 0.2, spin: 0.04 },
  3: { radius: 600, polar: 1.1, azimuth: 3, focus: 1, dead: 0.2, fixed: 0, shift: 0.2, spin: 0.1 },
  4: { radius: 720, polar: 0.95, azimuth: 3.7, focus: 1, dead: 0.15, fixed: 1, shift: 0.2, spin: 0.04 },
}

const buildingVertex = /* glsl */ `
  attribute float aStatus; attribute float aTarget; attribute float aDelay; attribute float aTop;
  uniform float uRise, uTime;
  varying vec3 vNormal; varying float vStatus, vTarget, vTop, vWorldY;
  void main() {
    float t = clamp((uRise - aDelay) / 0.28, 0.0, 1.0);
    float grow = 1.0 - pow(1.0 - t, 3.0);
    vec3 p = position;
    p.y *= grow;
    vNormal = normal; vStatus = aStatus; vTarget = aTarget; vTop = aTop; vWorldY = p.y;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(p, 1.0);
  }
`

const buildingFragment = /* glsl */ `
  uniform float uDead, uFocus, uFixed, uTime;
  varying vec3 vNormal; varying float vStatus, vTarget, vTop, vWorldY;
  void main() {
    float light = 0.5 + 0.5 * max(dot(normalize(vNormal), normalize(vec3(0.5, 0.8, 0.3))), 0.0);
    vec3 base = vec3(0.15, 0.125, 0.17);
    if (vStatus > 0.5 && vStatus < 1.5) base = vec3(0.23, 0.20, 0.26);
    if (vStatus > 2.5) base = vec3(0.05, 0.13, 0.09);
    vec3 color = base * light;
    color += vec3(0.05, 0.04, 0.07) * vTop;

    float isDead = step(1.5, vStatus) * step(vStatus, 2.5);
    float pulse = 0.82 + 0.18 * sin(uTime * 2.2 + vWorldY * 0.2);
    vec3 glow = vec3(1.0, 0.4, 0.05) * (0.75 + 0.5 * vTop) * pulse;
    color = mix(color, glow, isDead * uDead);

    color *= mix(1.0, 0.32, uFocus * (1.0 - vTarget));
    vec3 focused = mix(vec3(1.0, 0.42, 0.05), vec3(0.15, 0.85, 0.48), uFixed) * (0.62 + 0.3 * vTop);
    color = mix(color, focused, vTarget * uFocus);
    gl_FragColor = vec4(color, 1.0);
  }
`

const smokeVertex = /* glsl */ `
  attribute float aPhase; attribute float aTarget; attribute float aHeight;
  uniform float uTime, uDead, uFocus, uFixed, uRise, uPixel;
  varying float vAlpha;
  void main() {
    float life = fract(uTime * 0.09 + aPhase);
    vec3 p = position;
    p.y = aHeight + life * 260.0;
    p.x += sin(uTime * 0.4 + aPhase * 40.0) * 9.0 * life;
    p.z += cos(uTime * 0.3 + aPhase * 30.0) * 9.0 * life;
    float visible = aTarget > 0.5 ? max(uDead, uFocus) * (1.0 - uFixed) : uDead * (1.0 - uFocus * 0.8);
    vAlpha = sin(life * 3.14159) * visible * smoothstep(0.7, 1.0, uRise);
    vec4 view = modelViewMatrix * vec4(p, 1.0);
    gl_PointSize = uPixel * (3000.0 / -view.z) * (1.0 + life);
    gl_Position = projectionMatrix * view;
  }
`

const smokeFragment = /* glsl */ `
  varying float vAlpha;
  void main() {
    float d = length(gl_PointCoord - 0.5);
    gl_FragColor = vec4(1.0, 0.6, 0.2, smoothstep(0.5, 0.05, d) * vAlpha * 0.55);
  }
`

function buildGeometry(list: Building[]) {
  const pos: number[] = [], normal: number[] = [], status: number[] = [], target: number[] = [], delay: number[] = [], top: number[] = []
  const reach = Math.max(...list.flatMap((b) => b.p.map(Math.abs)))
  for (const b of list) {
    const pts: THREE.Vector2[] = []
    for (let i = 0; i < b.p.length; i += 2) pts.push(new THREE.Vector2(b.p[i], b.p[i + 1]))
    const cx = pts.reduce((a, v) => a + v.x, 0) / pts.length
    const cz = pts.reduce((a, v) => a + v.y, 0) / pts.length
    // Vertical scale is exaggerated so a low-rise township still reads as 3D.
    const h = b.s === 3 ? 0.6 : b.h * 4
    const d = Math.min(Math.hypot(cx, cz) / reach, 1) * 0.68 + Math.random() * 0.04
    const add = (x: number, y: number, z: number, nx: number, ny: number, nz: number, isTop: number) => {
      pos.push(x, y, z); normal.push(nx, ny, nz); status.push(b.s); target.push(b.t ? 1 : 0); delay.push(d); top.push(isTop)
    }
    const winding = THREE.ShapeUtils.isClockWise(pts) ? pts.slice().reverse() : pts
    for (const [a, c, e] of THREE.ShapeUtils.triangulateShape(winding, [])) {
      add(winding[a].x, h, winding[a].y, 0, 1, 0, 1)
      add(winding[e].x, h, winding[e].y, 0, 1, 0, 1)
      add(winding[c].x, h, winding[c].y, 0, 1, 0, 1)
    }
    for (let i = 0; i < winding.length; i++) {
      const u = winding[i], v = winding[(i + 1) % winding.length]
      const nx = v.y - u.y, nz = u.x - v.x, n = Math.hypot(nx, nz) || 1
      const [ax, az] = [nx / n, nz / n]
      add(u.x, 0, u.y, ax, 0, az, 0); add(v.x, 0, v.y, ax, 0, az, 0); add(v.x, h, v.y, ax, 0, az, 0.6)
      add(u.x, 0, u.y, ax, 0, az, 0); add(v.x, h, v.y, ax, 0, az, 0.6); add(u.x, h, u.y, ax, 0, az, 0.6)
    }
  }
  const g = new THREE.BufferGeometry()
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3))
  g.setAttribute('normal', new THREE.Float32BufferAttribute(normal, 3))
  g.setAttribute('aStatus', new THREE.Float32BufferAttribute(status, 1))
  g.setAttribute('aTarget', new THREE.Float32BufferAttribute(target, 1))
  g.setAttribute('aDelay', new THREE.Float32BufferAttribute(delay, 1))
  g.setAttribute('aTop', new THREE.Float32BufferAttribute(top, 1))
  return g
}

function buildSmoke(list: Building[], perBuilding: number) {
  const pos: number[] = [], phase: number[] = [], target: number[] = [], height: number[] = []
  for (const b of list.filter((x) => x.s === 2)) {
    for (let i = 0; i < perBuilding * (b.t ? 4 : 1); i++) {
      const k = Math.floor(Math.random() * (b.p.length / 2))
      pos.push(b.p[k * 2], 0, b.p[k * 2 + 1]); phase.push(Math.random()); target.push(b.t ? 1 : 0); height.push(b.h * 4)
    }
  }
  const g = new THREE.BufferGeometry()
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3))
  g.setAttribute('aPhase', new THREE.Float32BufferAttribute(phase, 1))
  g.setAttribute('aTarget', new THREE.Float32BufferAttribute(target, 1))
  g.setAttribute('aHeight', new THREE.Float32BufferAttribute(height, 1))
  return g
}

export async function startTownship(canvas: HTMLCanvasElement, opts: { still: boolean; light: boolean }): Promise<Scene3D> {
  const data: { b: Building[] } = await (await fetch('/landing/township.json')).json()

  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: 'high-performance' })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, opts.light ? 1.25 : 2))

  const scene = new THREE.Scene()
  scene.background = new THREE.Color(0x1c161b)
  scene.fog = new THREE.Fog(0x1c161b, 3000, 6500)
  const camera = new THREE.PerspectiveCamera(32, 1, 10, 9000)

  const shared = {
    uRise: { value: opts.still ? 2 : 0 }, uTime: { value: 0 },
    uDead: { value: 0 }, uFocus: { value: 0 }, uFixed: { value: 0 },
    uPixel: { value: renderer.getPixelRatio() * (opts.light ? 2.2 : 3) },
  }
  const buildings = new THREE.Mesh(buildGeometry(data.b), new THREE.ShaderMaterial({ vertexShader: buildingVertex, fragmentShader: buildingFragment, uniforms: shared }))
  scene.add(buildings)

  const smoke = new THREE.Points(buildSmoke(data.b, opts.light ? 3 : 7), new THREE.ShaderMaterial({
    vertexShader: smokeVertex, fragmentShader: smokeFragment, uniforms: shared,
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
  }))
  scene.add(smoke)

  const grid = new THREE.GridHelper(9000, 90, 0x4a3d4a, 0x352b35)
  grid.position.y = -1
  scene.add(grid)

  // Expanding rings mark the simulated years around the focus building.
  const focusB = data.b.find((b) => b.t)!
  let fx = 0, fz = 0
  for (let i = 0; i < focusB.p.length; i += 2) { fx += focusB.p[i]; fz += focusB.p[i + 1] }
  const focusPoint = new THREE.Vector3(fx / (focusB.p.length / 2), 12, fz / (focusB.p.length / 2))
  const rings = Array.from({ length: 5 }, (_, i) => {
    const m = new THREE.Mesh(new THREE.RingGeometry(0.97, 1, 72), new THREE.MeshBasicMaterial({ color: 0xf7931d, transparent: true, opacity: 0, side: THREE.DoubleSide, depthWrite: false, blending: THREE.AdditiveBlending }))
    m.rotation.x = -Math.PI / 2
    m.position.set(focusPoint.x, 2, focusPoint.z)
    m.userData.offset = i / 5
    scene.add(m)
    return m
  })

  let composer = opts.light ? null : new EffectComposer(renderer)
  if (composer) {
    composer.addPass(new RenderPass(scene, camera))
    composer.addPass(new UnrealBloomPass(new THREE.Vector2(256, 256), 0.7, 0.6, 0.5))
  }

  const size = () => {
    const w = window.innerWidth, h = window.innerHeight
    renderer.setSize(w, h, false)
    composer?.setSize(w, h)
    camera.aspect = w / h
    camera.updateProjectionMatrix()
  }
  size()
  window.addEventListener('resize', size)

  const narrow = () => window.innerWidth < 960
  const now = { ...BEATS[-1] }
  const origin = new THREE.Vector3(0, 0, 0)
  const center = origin.clone()
  const mouse = { x: 0, y: 0, sx: 0, sy: 0 }
  const onMove = (e: PointerEvent) => { mouse.x = e.clientX / window.innerWidth - 0.5; mouse.y = e.clientY / window.innerHeight - 0.5 }
  window.addEventListener('pointermove', onMove, { passive: true })

  let step = -1, heroScroll = 0, spin = 0, active = true, raf = 0, last = performance.now(), time = 0
  let slowFrames = 0, countedFrames = 0

  const draw = () => {
    const rad = Math.PI / 180
    const off = center
    const azimuth = now.azimuth + spin + mouse.sx * 8 * rad
    const polar = now.polar + heroScroll * 0.3 * (step === -1 ? 1 : 0) + mouse.sy * 4 * rad
    const radius = (narrow() ? now.radius * 1.7 : now.radius) * (1 - (step === -1 ? heroScroll * 0.2 : 0))
    camera.position.set(
      off.x + radius * Math.sin(polar) * Math.sin(azimuth),
      off.y + radius * Math.cos(polar),
      off.z + radius * Math.sin(polar) * Math.cos(azimuth),
    )
    camera.lookAt(off)
    const w = window.innerWidth, h = window.innerHeight
    camera.setViewOffset(w, h, narrow() ? 0 : now.shift * w, narrow() && step === -1 ? 0.2 * h : 0, w, h)
    rings.forEach((r) => {
      const p = (time * 0.18 + r.userData.offset) % 1
      r.scale.setScalar(30 + p * 300)
      ;(r.material as THREE.MeshBasicMaterial).opacity = (step === 3 ? 1 : 0) * (1 - p) * 0.8
    })
    if (composer) composer.render()
    else renderer.render(scene, camera)
  }

  const frame = (t: number) => {
    raf = requestAnimationFrame(frame)
    if (!active) { last = t; return }
    const raw = (t - last) / 1000
    const dt = Math.min(raw, 0.05)
    last = t
    // Slow machine: drop the glow pass and resolution once, so scrolling stays smooth.
    if (composer && ++countedFrames > 20) {
      if (raw > 0.04) slowFrames++
      if (countedFrames > 110) {
        if (slowFrames > 45) {
          composer.dispose()
          composer = null
          renderer.setPixelRatio(1)
          size()
        }
        countedFrames = 0
        slowFrames = 0
      }
    }
    time += dt
    shared.uTime.value = time
    if (shared.uRise.value < 2) shared.uRise.value += dt / 3.2
    const beat = BEATS[step]
    const ease = 1 - Math.exp(-dt * 2.4)
    now.radius += (beat.radius - now.radius) * ease
    now.polar += (beat.polar - now.polar) * ease
    now.azimuth += (beat.azimuth - now.azimuth) * ease
    now.shift += (beat.shift - now.shift) * ease
    now.focus += (beat.focus - now.focus) * ease
    now.fixed += (beat.fixed - now.fixed) * ease
    const deadTarget = shared.uRise.value > 0.75 ? beat.dead : 0
    now.dead += (deadTarget - now.dead) * ease
    shared.uDead.value = now.dead
    shared.uFocus.value = now.focus
    shared.uFixed.value = now.fixed
    center.lerp(step >= 2 ? focusPoint : origin, ease)
    spin = (spin + dt * beat.spin) % (Math.PI * 2)
    mouse.sx += (mouse.x - mouse.sx) * ease
    mouse.sy += (mouse.y - mouse.sy) * ease
    draw()
  }

  if (opts.still) {
    now.dead = 1
    shared.uDead.value = 1
    draw()
  } else {
    raf = requestAnimationFrame(frame)
  }

  return {
    setStep(s) {
      step = s
      if (opts.still) {
        const b = BEATS[s]
        Object.assign(now, b)
        center.copy(s >= 2 ? focusPoint : origin)
        shared.uDead.value = b.dead; shared.uFocus.value = b.focus; shared.uFixed.value = b.fixed
        draw()
      }
    },
    setScroll(t) { heroScroll = t },
    setActive(on) { active = on },
    dispose() {
      cancelAnimationFrame(raf)
      window.removeEventListener('resize', size)
      window.removeEventListener('pointermove', onMove)
      scene.traverse((o) => {
        const m = o as THREE.Mesh
        m.geometry?.dispose()
        const mat = m.material as THREE.Material | undefined
        mat?.dispose?.()
      })
      composer?.dispose()
      renderer.dispose()
    },
  }
}
