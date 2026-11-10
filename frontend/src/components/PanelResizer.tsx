// Drag handle on the side panel's inner edge (the edge facing the map), plus
// the width state behind it. Desktop only: below MOBILE_BREAKPOINT the handle
// is not rendered and the panel uses its default width.

import { useCallback, useEffect, useRef, useState } from 'react'

export const PANEL_DEFAULT_WIDTH = 440
export const MOBILE_BREAKPOINT = 768
const STORAGE_KEY = 'lm_panel_width'
const MAP_RESIZE_MS = 50

const maxWidth = () => Math.max(PANEL_DEFAULT_WIDTH, Math.floor(window.innerWidth * 0.5))
const clamp = (w: number) => Math.min(maxWidth(), Math.max(PANEL_DEFAULT_WIDTH, Math.round(w)))

function readStored(): number {
  try {
    const v = Number(localStorage.getItem(STORAGE_KEY))
    return Number.isFinite(v) && v > 0 ? clamp(v) : PANEL_DEFAULT_WIDTH
  } catch {
    return PANEL_DEFAULT_WIDTH
  }
}

function store(w: number | null) {
  try {
    if (w === null) localStorage.removeItem(STORAGE_KEY)
    else localStorage.setItem(STORAGE_KEY, String(w))
  } catch { /* storage unavailable: width just isn't remembered */ }
}

/**
 * Panel width (persisted per viewer) and resize callbacks.
 * `onMapResize` is called throttled while dragging and once when a drag ends,
 * so the MapLibre canvas (and the Three.js layer drawing into it) re-fits.
 */
export function usePanelWidth(onMapResize: () => void) {
  const [width, setWidth] = useState<number>(() => readStored())
  const [narrow, setNarrow] = useState(() => window.innerWidth < MOBILE_BREAKPOINT)
  const last = useRef(0)
  const trailing = useRef<number | undefined>(undefined)

  const resizeMap = useCallback((force = false) => {
    window.clearTimeout(trailing.current)
    const now = performance.now()
    if (force || now - last.current >= MAP_RESIZE_MS) {
      last.current = now
      onMapResize()
    } else {
      // Trailing call, so the final drag position always gets a resize.
      trailing.current = window.setTimeout(() => { last.current = performance.now(); onMapResize() }, MAP_RESIZE_MS)
    }
  }, [onMapResize])

  // Keep within [default, 50% of window] when the window changes size.
  useEffect(() => {
    const onWin = () => {
      setNarrow(window.innerWidth < MOBILE_BREAKPOINT)
      setWidth((w) => clamp(w))
      // MapLibre measures on its own window listener, possibly before the
      // clamped panel width is laid out; measure again next frame.
      requestAnimationFrame(() => onMapResize())
    }
    window.addEventListener('resize', onWin)
    return () => window.removeEventListener('resize', onWin)
  }, [onMapResize])

  const dragTo = useCallback((clientX: number) => {
    // The panel is docked on the right, so its width is the distance to the window's right edge.
    setWidth(clamp(window.innerWidth - clientX))
    resizeMap()
  }, [resizeMap])

  const endDrag = useCallback(() => {
    setWidth((w) => { store(w); return w })
    resizeMap(true)
  }, [resizeMap])

  const reset = useCallback(() => {
    setWidth(PANEL_DEFAULT_WIDTH)
    store(null)
    // Wait one frame so the new width is laid out before the map measures.
    requestAnimationFrame(() => resizeMap(true))
  }, [resizeMap])

  return {
    width: narrow ? PANEL_DEFAULT_WIDTH : width,
    resizable: !narrow,
    dragTo, endDrag, reset,
  }
}

export function PanelResizer({ onDrag, onEnd, onReset }: {
  onDrag: (clientX: number) => void
  onEnd: () => void
  onReset: () => void
}) {
  const [dragging, setDragging] = useState(false)

  return (
    <div className="panel-resizer" aria-hidden="true">
      <div
        className={`panel-resizer-hit${dragging ? ' dragging' : ''}`}
        title="Drag to resize · double-click to reset"
        onPointerDown={(e) => {
          if (e.button !== 0) return
          e.preventDefault()
          e.currentTarget.setPointerCapture(e.pointerId)
          setDragging(true)
          document.body.classList.add('is-resizing')
        }}
        onPointerMove={(e) => { if (dragging) onDrag(e.clientX) }}
        onPointerUp={(e) => {
          if (!dragging) return
          e.currentTarget.releasePointerCapture(e.pointerId)
          setDragging(false)
          document.body.classList.remove('is-resizing')
          onEnd()
        }}
        onPointerCancel={() => {
          setDragging(false)
          document.body.classList.remove('is-resizing')
          onEnd()
        }}
        onDoubleClick={onReset}
      >
        <span className="panel-resizer-grip" />
      </div>
    </div>
  )
}
