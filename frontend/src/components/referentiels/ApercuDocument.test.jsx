/**
 * Tests de l'aperçu du document dans la page.
 *
 * Cet aperçu est le seul moyen de montrer un export dans un environnement qui
 * interdit à la fois les téléchargements et les fenêtres surgissées : un
 * échec silencieux y serait exactement le symptôme que l'on cherche à
 * supprimer (« je clique et rien ne se passe »).
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import ApercuDocument from './ApercuDocument'

const CSV = 'code,libelle\nM1,Mention une\nM2,Mention deux\n'

describe('Aperçu du document exporté', () => {
  beforeEach(() => {
    window.URL.createObjectURL = vi.fn(() => 'blob:apercu')
    window.URL.revokeObjectURL = vi.fn()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('affiche le contenu d’un CSV et propose de le copier', async () => {
    const blob = new Blob([CSV], { type: 'text/csv; charset=utf-8' })
    render(<ApercuDocument nom="mentions.csv" blob={blob} contentType="text/csv" />)

    await waitFor(() => expect(screen.getByText(/Mention une/)).toBeTruthy())
    expect(screen.getByText(/Contenu du fichier/)).toBeTruthy()
    expect(screen.getByRole('button', { name: /Copier/i })).toBeTruthy()
  })

  it('rend un PDF dans un cadre, sans tenter de le télécharger', async () => {
    const pdf = new Blob([new Uint8Array([0x25, 0x50, 0x44, 0x46])], {
      type: 'application/pdf',
    })
    render(<ApercuDocument nom="mentions.pdf" blob={pdf} contentType="application/pdf" />)

    await waitFor(() => expect(screen.getByTitle('Aperçu de mentions.pdf')).toBeTruthy())
    const cadre = screen.getByTitle('Aperçu de mentions.pdf')
    expect(cadre.tagName).toBe('IFRAME')
    expect(cadre.getAttribute('src')).toBe('blob:apercu')
  })

  it('copie le contenu dans le presse-papiers sur demande', async () => {
    const ecrire = vi.fn(async () => {})
    vi.stubGlobal('navigator', { ...navigator, clipboard: { writeText: ecrire } })

    const blob = new Blob([CSV], { type: 'text/csv; charset=utf-8' })
    render(<ApercuDocument nom="mentions.csv" blob={blob} contentType="text/csv" />)

    const bouton = await screen.findByRole('button', { name: /Copier/i })
    bouton.click()
    await waitFor(() => expect(ecrire).toHaveBeenCalledWith(CSV))
    vi.unstubAllGlobals()
  })

  it('annonce clairement un format non affichable au lieu de rester muet', async () => {
    const xlsx = new Blob([new Uint8Array([0x50, 0x4b, 0x03, 0x04])], {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    })
    render(<ApercuDocument nom="mentions.xlsx" blob={xlsx} contentType="application/vnd…sheet" />)

    await waitFor(() =>
      expect(screen.getByText(/ne peut pas être affiché ici/)).toBeTruthy(),
    )
    // Le message doit rassurer : le document existe, seul l'affichage manque.
    expect(screen.getByText(/bien été généré/)).toBeTruthy()
  })
})
