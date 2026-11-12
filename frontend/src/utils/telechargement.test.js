/**
 * Tests de l'utilitaire de téléchargement partagé.
 *
 * Ce module remplace 28 blocs copiés-collés : il porte donc à lui seul la
 * garantie que tout bouton d'export de l'application télécharge réellement.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { estUnDocument, telechargerBlob, telechargerReponseBlob } from './telechargement'

/** Installe les doublons du navigateur et enregistre les appels. */
function installerNavigateur() {
  const appels = { cree: [], revoque: [], clics: [] }
  const originalCree = window.URL.createObjectURL
  const originalRevoque = window.URL.revokeObjectURL
  const originalClick = HTMLAnchorElement.prototype.click

  window.URL.createObjectURL = vi.fn((blob) => {
    appels.cree.push(blob)
    return 'blob:test'
  })
  window.URL.revokeObjectURL = vi.fn((url) => {
    appels.revoque.push(url)
  })
  // jsdom ne télécharge rien : on intercepte le clic pour lire `download`.
  HTMLAnchorElement.prototype.click = vi.fn(function () {
    appels.clics.push({ nom: this.download, href: this.href })
  })

  return {
    appels,
    restaurer() {
      window.URL.createObjectURL = originalCree
      window.URL.revokeObjectURL = originalRevoque
      HTMLAnchorElement.prototype.click = originalClick
    },
  }
}

describe('Utilitaire de téléchargement — détection du type', () => {
  it('accepte un PDF, un Word, un Excel et un CSV', () => {
    for (const type of [
      'application/pdf',
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      'text/csv;charset=utf-8',
      'application/octet-stream',
    ]) {
      expect(estUnDocument(new Blob(['x']), type)).toBe(true)
    }
  })

  it('refuse une réponse d’erreur JSON ou HTML', () => {
    expect(estUnDocument(new Blob(['{"detail":"refusé"}']), 'application/json')).toBe(false)
    expect(estUnDocument(new Blob(['<html>']), 'text/html')).toBe(false)
  })

  it('ne bloque pas un type inconnu ou absent', () => {
    // Mieux vaut tenter le téléchargement que refuser un document valide
    // dont le serveur n'a pas déclaré le type.
    expect(estUnDocument(new Blob(['x']), '')).toBe(true)
    expect(estUnDocument(new Blob(['x']), 'application/x-format-maison')).toBe(true)
  })

  it('refuse l’absence de contenu', () => {
    expect(estUnDocument(null)).toBe(false)
    expect(estUnDocument(undefined)).toBe(false)
  })
})

describe('Utilitaire de téléchargement — déclenchement', () => {
  let nav

  beforeEach(() => {
    nav = installerNavigateur()
  })

  afterEach(() => {
    nav.restaurer()
    vi.useRealTimers()
  })

  it('crée un lien de téléchargement nommé puis le clique', () => {
    const blob = new Blob(['%PDF-1.4'], { type: 'application/pdf' })
    const nom = telechargerBlob(blob, 'referentiel.pdf')

    expect(nom).toBe('referentiel.pdf')
    expect(nav.appels.cree).toEqual([blob])
    expect(nav.appels.clics).toEqual([{ nom: 'referentiel.pdf', href: 'blob:test' }])
  })

  it('ne révoque pas l’URL immédiatement', () => {
    // C’est la correction du bug : révoquer juste après `click()` peut
    // annuler un téléchargement qui n’a pas encore démarré (Safari, Firefox).
    telechargerBlob(new Blob(['x'], { type: 'text/csv' }), 'a.csv')
    expect(nav.appels.revoque).toEqual([])
  })

  it('révoque l’URL après un délai, pour libérer la mémoire', () => {
    vi.useFakeTimers()
    telechargerBlob(new Blob(['x'], { type: 'text/csv' }), 'a.csv')
    expect(nav.appels.revoque).toEqual([])

    vi.advanceTimersByTime(120_000)
    expect(nav.appels.revoque).toEqual(['blob:test'])
  })

  it('ne télécharge rien si le serveur a renvoyé du JSON', () => {
    expect(() =>
      telechargerBlob(new Blob(['{"detail":"refusé"}']), 'erreur.json', {
        contentType: 'application/json',
      }),
    ).toThrow(/aucun document/i)
    expect(nav.appels.cree).toEqual([])
    expect(nav.appels.clics).toEqual([])
  })

  it('retire le lien du document après le clic', () => {
    telechargerBlob(new Blob(['x'], { type: 'application/pdf' }), 'a.pdf')
    // Aucun <a> résiduel ne doit rester dans le corps du document.
    expect(document.querySelectorAll('a[download]')).toHaveLength(0)
  })

  it('accepte directement le résultat de api.getBlob', () => {
    const nom = telechargerReponseBlob(
      { blob: new Blob(['PK'], { type: 'application/zip' }), fileName: 'serveur.xlsx' },
      'defaut.xlsx',
    )
    expect(nom).toBe('serveur.xlsx')
    expect(nav.appels.clics).toHaveLength(1)
  })

  it('retombe sur le nom par défaut si le serveur n’en fournit pas', () => {
    const nom = telechargerReponseBlob(
      { blob: new Blob(['PK'], { type: 'application/zip' }) },
      'defaut.xlsx',
    )
    expect(nom).toBe('defaut.xlsx')
  })
})
