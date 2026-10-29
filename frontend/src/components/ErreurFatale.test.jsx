import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import ErreurFatale from './ErreurFatale'

/** Composant qui échoue au rendu, comme un écran dont une donnée manque. */
function Explose() {
  throw new Error('Donnée pédagogique absente')
}

function Fonctionne() {
  return <p>Écran affiché normalement</p>
}

describe('Garde-fou d’affichage — plus jamais de page blanche', () => {
  let consoleError
  beforeEach(() => {
    // React journalise l'erreur interceptée : on la neutralise pour la sortie.
    consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
  })
  afterEach(() => {
    consoleError.mockRestore()
  })

  it('affiche les enfants quand tout va bien', () => {
    render(
      <ErreurFatale>
        <Fonctionne />
      </ErreurFatale>,
    )
    expect(screen.getByText('Écran affiché normalement')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('remplace le silence par un message lisible quand un écran plante', () => {
    render(
      <ErreurFatale>
        <Explose />
      </ErreurFatale>,
    )
    const alerte = screen.getByRole('alert')
    expect(alerte).toBeInTheDocument()
    expect(screen.getByText(/n’a pas pu s’afficher/i)).toBeInTheDocument()
    // Le message réel de l'erreur est conservé : il sert au diagnostic.
    expect(screen.getByText(/Donnée pédagogique absente/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Recharger la page/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Revenir à l’accueil/i })).toBeInTheDocument()
  })

  it('ne divulgue pas de trace technique par défaut', () => {
    render(
      <ErreurFatale>
        <Explose />
      </ErreurFatale>,
    )
    // Le détail est replié : l'utilisateur non technique n'a pas la pile à l'écran.
    const details = screen.getByText(/Détail technique/i).closest('details')
    expect(details).not.toHaveAttribute('open')
  })
})
