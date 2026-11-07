import { StrictMode, Suspense, lazy, useSyncExternalStore } from 'react'
import { createRoot } from 'react-dom/client'
import './styles.css'
import { Landing } from './Landing.tsx'

// Loaded on demand so the landing page does not download the map library.
const App = lazy(() => import('./App.tsx'))

const subscribe = (fn: () => void) => {
  window.addEventListener('hashchange', fn)
  return () => window.removeEventListener('hashchange', fn)
}

function Root() {
  const isDemo = useSyncExternalStore(subscribe, () => window.location.hash === '#/demo')
  return isDemo ? <Suspense fallback={null}><App /></Suspense> : <Landing />
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Root />
  </StrictMode>,
)
