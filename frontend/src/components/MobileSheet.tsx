// Mobile only (< 768px): bottom sheet for the AssetPanel, and a side drawer
// for the flagged-asset list / history. Desktop never renders these.

import { useRef, useState, type ReactNode } from 'react'

const DRAG_THRESHOLD = 40 // px of vertical drag that counts as a swipe

/**
 * Collapsed: fits its content (header + core metrics). Expanded: ~85% of the
 * viewport. Tap the grab bar to toggle; swipe up to expand, swipe down to
 * collapse (or to dismiss when already collapsed).
 */
export function MobileSheet({ expanded, onExpandedChange, onDismiss, children }: {
  expanded: boolean
  onExpandedChange: (expanded: boolean) => void
  onDismiss: () => void
  children: ReactNode
}) {
  const startY = useRef<number | null>(null)
  const dragged = useRef(false)
  const [dy, setDy] = useState(0)

  const end = () => {
    if (startY.current === null) return
    startY.current = null
    if (dy < -DRAG_THRESHOLD) onExpandedChange(true)
    else if (dy > DRAG_THRESHOLD) { if (expanded) onExpandedChange(false); else onDismiss() }
    setDy(0)
  }

  return (
    <div
      className={`m-sheet ${expanded ? 'expanded' : 'collapsed'}`}
      // Follow the finger downwards for feedback; upward swipes just expand on release.
      style={dy > 0 ? { transform: `translateY(${dy}px)` } : undefined}
    >
      <button
        className="m-sheet-grab"
        aria-label={expanded ? 'Collapse details' : 'Expand details'}
        aria-expanded={expanded}
        onPointerDown={(e) => {
          startY.current = e.clientY
          dragged.current = false
          e.currentTarget.setPointerCapture(e.pointerId)
        }}
        onPointerMove={(e) => {
          if (startY.current === null) return
          const d = e.clientY - startY.current
          if (Math.abs(d) > 6) dragged.current = true
          setDy(d)
        }}
        onPointerUp={end}
        onPointerCancel={() => { startY.current = null; setDy(0) }}
        onClick={() => {
          // A drag already decided the outcome on pointer-up; a tap toggles.
          if (dragged.current) { dragged.current = false; return }
          onExpandedChange(!expanded)
        }}
      >
        <span className="m-sheet-grip" />
      </button>
      <div className="m-sheet-body">{children}</div>
    </div>
  )
}

export function MobileDrawer({ title, onClose, children }: {
  title: string
  onClose: () => void
  children: ReactNode
}) {
  return (
    <>
      <div className="m-drawer-backdrop" onClick={onClose} />
      <div className="m-drawer" role="dialog" aria-label={title}>
        <div className="m-drawer-head">
          <span className="m-drawer-title">{title}</span>
          <button className="m-icon-btn" onClick={onClose} aria-label="Close">×</button>
        </div>
        <div className="m-drawer-body">{children}</div>
      </div>
    </>
  )
}
