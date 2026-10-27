import { describe, it, expect, afterEach } from 'vitest'
import { safeLocalStorage } from './safeStorage'

const CLE = 'test_safe_storage'

describe('safeLocalStorage — stockage résilient (aperçu iframe)', () => {
  const originalLocalStorage = window.localStorage

  afterEach(() => {
    // Restaure le stockage réel après chaque simulation de panne.
    Object.defineProperty(window, 'localStorage', {
      value: originalLocalStorage,
      configurable: true,
    })
    safeLocalStorage.removeItem(CLE)
  })

  it('écrit, lit et supprime via localStorage quand il est disponible', () => {
    safeLocalStorage.setItem(CLE, 'valeur')
    expect(safeLocalStorage.getItem(CLE)).toBe('valeur')
    safeLocalStorage.removeItem(CLE)
    expect(safeLocalStorage.getItem(CLE)).toBeNull()
  })

  it("survit à un localStorage qui lève SecurityError (iframe tierce bloquée)", () => {
    const bloque = {
      setItem: () => { throw new DOMException('Access denied', 'SecurityError') },
      getItem: () => { throw new DOMException('Access denied', 'SecurityError') },
      removeItem: () => { throw new DOMException('Access denied', 'SecurityError') },
    }
    Object.defineProperty(window, 'localStorage', { value: bloque, configurable: true })

    expect(() => safeLocalStorage.setItem(CLE, 'jeton')).not.toThrow()
    // Le repli mémoire conserve la valeur pour la session courante.
    expect(safeLocalStorage.getItem(CLE)).toBe('jeton')
    expect(() => safeLocalStorage.removeItem(CLE)).not.toThrow()
    expect(safeLocalStorage.getItem(CLE)).toBeNull()
  })

  it('getItem renvoie null (et non une exception) sans stockage du tout', () => {
    Object.defineProperty(window, 'localStorage', {
      value: undefined,
      configurable: true,
    })
    // sessionStorage reste disponible dans jsdom : la sonde bascule dessus.
    expect(safeLocalStorage.getItem(CLE)).toBeNull()
  })

  it("convertit les valeurs non textuelles en chaîne (comme l'API Storage)", () => {
    safeLocalStorage.setItem(CLE, 42)
    expect(safeLocalStorage.getItem(CLE)).toBe('42')
  })
})
