import '@testing-library/jest-dom/vitest'
import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'

// jsdom ne fournit pas ces API navigateur pourtant utilisées par certaines
// pages (graphiques, observateurs, défilement, media queries). On fournit des
// polyfils inertes mais sûrs, sans modifier le code applicatif.

// Node 26 expose une API localeStorage expérimentale qui peut être
// absente dans le contexte Vitest/jsdom. Les pages et les tests utilisent
// toutefois le Storage standard du navigateur. On installe donc un Storage
// mémoire uniquement lorsque jsdom ne fournit pas l'API, sans modifier les
// assertions ni les appels clear() des tests.
const createMemoryStorage = () => {
  const values = new Map()
  return {
    get length() { return values.size },
    key(index) { return [...values.keys()][index] ?? null },
    getItem(key) { return values.has(String(key)) ? values.get(String(key)) : null },
    setItem(key, value) { values.set(String(key), String(value)) },
    removeItem(key) { values.delete(String(key)) },
    clear() { values.clear() },
  }
}

if (!window.localStorage) {
  Object.defineProperty(window, 'localStorage', {
    configurable: true,
    value: createMemoryStorage(),
  })
}
if (!window.sessionStorage) {
  Object.defineProperty(window, 'sessionStorage', {
    configurable: true,
    value: createMemoryStorage(),
  })
}

if (!window.matchMedia) {
  window.matchMedia = (query) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })
}

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
window.ResizeObserver = window.ResizeObserver || ResizeObserverStub

class IntersectionObserverStub {
  constructor(cb) {
    this.cb = cb
  }
  observe() {}
  unobserve() {}
  disconnect() {}
  takeRecords() {
    return []
  }
}
window.IntersectionObserver = window.IntersectionObserver || IntersectionObserverStub

if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = function scrollIntoView() {}
}

if (!window.HTMLCanvasElement.prototype.getContext) {
  window.HTMLCanvasElement.prototype.getContext = function getContext() {
    return null
  }
}

// jsdom n'implémente pas layout : offsetWidth/Height valent 0, ce qui casse
// certains calculateurs de positionnement de menu. Valeurs déterministes.
Object.defineProperty(window.HTMLElement.prototype, 'offsetWidth', {
  configurable: true,
  get() {
    return 1000
  },
})
Object.defineProperty(window.HTMLElement.prototype, 'offsetHeight', {
  configurable: true,
  get() {
    return 800
  },
})

// Chaque test repart d'un stockage et de fetch propres.
afterEach(() => {
  cleanup()
  window.localStorage.clear()
  window.sessionStorage.clear()
  vi.restoreAllMocks()
})
