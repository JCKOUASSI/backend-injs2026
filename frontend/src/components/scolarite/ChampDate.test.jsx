/**
 * Tests du champ date partagé (saisie JJ/MM/AAAA + calendrier premium).
 *
 * Deux usages couverts :
 *  - dates de naissance (défaut) : calendrier reculé de 20 ans, futur interdit ;
 *  - dates de planification (campagnes, épreuves) : `reculAnnees={0}` et
 *    `futurInterdit={false}` — le calendrier s'ouvre au mois courant et les
 *    dates à venir sont choisissables.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import ChampDate, {
  MOIS_FR, dateFrancaiseVersIso, erreurDateFrancaise, isoVersDateFrancaise,
} from './ChampDate'

function libelleJour(date) {
  return `${date.getDate()} ${MOIS_FR[date.getMonth()]} ${date.getFullYear()}`
}

describe('ChampDate — utilitaires', () => {
  it('convertit ISO vers JJ/MM/AAAA et inversement', () => {
    expect(isoVersDateFrancaise('2027-03-14')).toBe('14/03/2027')
    expect(isoVersDateFrancaise('')).toBe('')
    expect(isoVersDateFrancaise(null)).toBe('')
    expect(dateFrancaiseVersIso(isoVersDateFrancaise('2000-02-29'))).toBe('2000-02-29')
  })

  it('valide une date générique avec un libellé contextualisé', () => {
    expect(erreurDateFrancaise('')).toBe('')
    expect(erreurDateFrancaise('14/03/2027')).toBe('')
    expect(erreurDateFrancaise('31/02/2027', 'La date d’ouverture'))
      .toMatch(/^La date d’ouverture est invalide/)
  })
})

describe('ChampDate — calendrier', () => {
  it('par défaut : ouverture 20 ans en arrière, dates futures désactivées', () => {
    render(<ChampDate id="d1" valeur="" onChange={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: /ouvrir le calendrier/i }))
    const selectAnnee = screen.getByRole('combobox', { name: /année affichée/i })
    expect(Number(selectAnnee.value)).toBe(new Date().getFullYear() - 20)
    // La navigation vers le mois suivant reste possible (mois passé).
    expect(screen.getByRole('button', { name: /mois suivant/i })).not.toBeDisabled()
  })

  it('planification : mois courant, demain choisissable', () => {
    const onChange = vi.fn()
    render(
      <ChampDate
        id="d2" valeur="" onChange={onChange}
        reculAnnees={0} futurInterdit={false}
        etiquetteCalendrier="Choisir la date d’ouverture"
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: /ouvrir le calendrier/i }))
    expect(screen.getByRole('dialog', { name: /choisir la date d’ouverture/i })).toBeInTheDocument()
    const selectAnnee = screen.getByRole('combobox', { name: /année affichée/i })
    expect(Number(selectAnnee.value)).toBe(new Date().getFullYear())

    const demain = new Date()
    demain.setDate(demain.getDate() + 1)
    const boutonDemain = screen.getByRole('button', { name: libelleJour(demain) })
    expect(boutonDemain).not.toBeDisabled()
    fireEvent.click(boutonDemain)
    const jj = String(demain.getDate()).padStart(2, '0')
    const mm = String(demain.getMonth() + 1).padStart(2, '0')
    expect(onChange).toHaveBeenCalledWith(`${jj}/${mm}/${demain.getFullYear()}`)
  })

  it('signale aria-invalid sur une date complète mais inexistante', () => {
    render(<ChampDate id="d3" valeur="31/02/2027" onChange={vi.fn()} />)
    expect(screen.getByPlaceholderText('JJ/MM/AAAA')).toHaveAttribute('aria-invalid', 'true')
  })
})
