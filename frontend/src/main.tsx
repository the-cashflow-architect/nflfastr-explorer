import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import { revealApp } from './lib/native'
import { seedIfEmpty } from './lib/offline'
import './index.css'

// On a fresh install the snapshot bundled with the app is written into the
// cache before anything renders, so the first screen is the home page rather
// than a 43-second wait. Everywhere else this returns immediately.
void seedIfEmpty().finally(() => {
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <App />
    </StrictMode>,
  )
  revealApp()
})
