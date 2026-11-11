// The single "is this a phone-sized viewport?" check. Every mobile-only
// behaviour (layout, map pixel ratio, Three.js quality) branches on this,
// and the CSS uses the same breakpoint (@media (max-width: 767px)).
// Desktop (>= 768px) never takes a mobile branch.

import { useEffect, useState } from 'react'
import { MOBILE_BREAKPOINT } from './components/PanelResizer'

export const MOBILE_QUERY = `(max-width: ${MOBILE_BREAKPOINT - 1}px)`

/** Snapshot, for things decided once at start-up (map pixel ratio, 3D quality). */
export function isMobileViewport(): boolean {
  return typeof window !== 'undefined' && !!window.matchMedia?.(MOBILE_QUERY).matches
}

/** Live value, for layout. */
export function useIsMobile(): boolean {
  const [mobile, setMobile] = useState(isMobileViewport)
  useEffect(() => {
    const mq = window.matchMedia(MOBILE_QUERY)
    const on = () => setMobile(mq.matches)
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [])
  return mobile
}

/** Mobile render settings. Desktop values are the unchanged originals. */
export const MOBILE_PERF = {
  maxPixelRatio: 1.5,
  /** Share of the desktop tree / canopy instance caps used on mobile. */
  treeScale: 0.3,
} as const
