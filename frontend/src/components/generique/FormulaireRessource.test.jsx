/**
 * Formulaire générique de référentiel — saisie, envoi, refus serveur.
 *
 * Ce composant est la pièce neuve du CRUD Référentiels : jusqu'ici les écrans
 * ne savaient qu'afficher. Les tests vérifient ce qui compte pour un
 * formulaire d'administration : les champs déclarés sont les seuls affichés,
 * le corps envoyé respecte les types (un identifiant reste un nombre), le
 * serveur reste juge des erreurs, et rien n'est créé sans les champs requis.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

import { apiController } from '@/test/utils/mockApi'
import { AllProviders } from '@/test/utils/renderWithProviders'
import FormulaireRessource, {
  valeursFormulaire,
  corpsRequete,
  champsManquants,
} from './FormulaireRessource'

const FORMULAIRE = {
  titreCreation: 'Créer un niveau',
  titreModification: 'Modifier le niveau',
  champs: [
    { cle: 'code', libelle: 'Code', requis: true },
    { cle: 'libelle', libelle: 'Libellé', requis: true },
    { cle: 'cycle', libelle: 'Cycle', type: 'select', requis: true, options: [
      { valeur: 'LICENCE', libelle: 'Licence' },
      { valeur: 'MASTER', libelle: 'Master' },
    ] },
    { cle: 'ordre', libelle: 'Ordre', type: 'nombre', requis: true, min: 1 },
    { cle: 'credits_requis', libelle: 'Crédits requis', type: 'nombre' },
    { cle: 'actif', libelle: 'Actif', type: 'booleen', defaut: true },
  ],
  creation: { chemin: '/scolarite/ref/niveaux/' },
  modification: (l) => ({ chemin: `/scolarite/ref/niveaux/${l.id}/` }),
}

const ECRAN = { id: 'niveaux', titre: 'Niveaux' }

function monter({ formulaire = FORMULAIRE, ligne = null, onFermer = vi.fn(), onEnregistre = vi.fn() } = {}) {
  return render(
    <FormulaireRessource
      formulaire={formulaire}
      ligne={ligne}
      ecran={ECRAN}
      onFermer={onFermer}
      onEnregistre={onEnregistre}
    />,
    { wrapper: ({ children }) => <AllProviders routePattern="*">{children}</AllProviders> },
  )
}

beforeEach(() => {
  apiController.setRoute('/scolarite/ref/niveaux/', [])
})

afterEach(() => {
  cleanup()
  apiController.reset()
})

describe('fonctions de sérialisation', () => {
  it('pré-remplit un défaut déclaré et laisse les autres champs vides', () => {
    const valeurs = valeursFormulaire(FORMULAIRE.champs)
    expect(valeurs.actif).toBe(true)
    expect(valeurs.code).toBe('')
    expect(valeurs.credits_requis).toBe('')
  })

  it('convertit les valeurs de la ligne en chaînes éditables', () => {
    const valeurs = valeursFormulaire(FORMULAIRE.champs, {
      id: 3, code: 'L1', libelle: 'Licence 1', cycle: 'LICENCE',
      ordre: 1, credits_requis: null, actif: 0,
    })
    expect(valeurs.ordre).toBe('1')
    expect(valeurs.actif).toBe(false)
    expect(valeurs.credits_requis).toBe('')
  })

  it('envoie des nombres typés et omet les vides en création', () => {
    const valeurs = { code: 'L2', libelle: 'Licence 2', cycle: 'LICENCE', ordre: '2', credits_requis: '', actif: true }
    const corps = corpsRequete(FORMULAIRE.champs, valeurs, { creation: true })
    expect(corps.ordre).toBe(2)
    expect(corps).not.toHaveProperty('credits_requis')
    expect(corps.actif).toBe(true)
  })

  it('transmet null en modification pour un nombre effacé (pas zéro)', () => {
    const valeurs = { code: 'L2', libelle: 'Licence 2', cycle: 'LICENCE', ordre: '2', credits_requis: '', actif: true }
    const corps = corpsRequete(FORMULAIRE.champs, valeurs, { creation: false })
    expect(corps.credits_requis).toBeNull()
    expect(corps.credits_requis).not.toBe(0)
  })

  it('signale les champs obligatoires manquants', () => {
    const manquants = champsManquants(FORMULAIRE.champs, { code: '', libelle: 'X', cycle: '', ordre: '', actif: false })
    expect(manquants).toEqual(['Code', 'Cycle', 'Ordre'])
  })
})

describe('rendu du formulaire', () => {
  it('affiche les champs déclarés et le bouton de création', () => {
    monter()
    expect(screen.getByRole('dialog')).toHaveAttribute('aria-modal', 'true')
    expect(screen.getByTestId('champ-code')).toBeTruthy()
    expect(screen.getByTestId('champ-cycle').tagName).toBe('SELECT')
    expect(screen.getByTestId('form-enregistrer').textContent).toBe('Créer')
    expect(screen.getByText('Créer un niveau')).toBeTruthy()
  })

  it('ne permet pas de soumettre sans les champs obligatoires (aucun appel réseau)', async () => {
    monter()
    await userEvent.click(screen.getByTestId('form-enregistrer'))
    expect(screen.getByTestId('form-erreur').textContent).toMatch(/Champs obligatoires manquants/)
    expect(apiController.api.post).not.toHaveBeenCalled()
  })

  it('crée la ligne puis prévient l’écran porteur', async () => {
    const onEnregistre = vi.fn()
    monter({ onEnregistre })
    await userEvent.type(screen.getByTestId('champ-code'), 'L2')
    await userEvent.type(screen.getByTestId('champ-libelle'), 'Licence 2')
    await userEvent.selectOptions(screen.getByTestId('champ-cycle'), 'LICENCE')
    await userEvent.type(screen.getByTestId('champ-ordre'), '2')
    await userEvent.click(screen.getByTestId('form-enregistrer'))

    await waitFor(() => expect(onEnregistre).toHaveBeenCalledWith('Élément créé.'))
    const [chemin, corps] = apiController.findCall('post', '/scolarite/ref/niveaux/')
    expect(chemin).toBe('/scolarite/ref/niveaux/')
    expect(corps).toMatchObject({ code: 'L2', libelle: 'Licence 2', cycle: 'LICENCE', ordre: 2 })
    // Le champ vide non obligatoire est omis : le serveur applique son défaut.
    expect(corps).not.toHaveProperty('credits_requis')
  })

  it('modifie une ligne existante par PATCH sur son identifiant', async () => {
    const onEnregistre = vi.fn()
    monter({
      ligne: { id: 7, code: 'L1', libelle: 'Licence 1', cycle: 'LICENCE', ordre: 1, credits_requis: 60, actif: true },
      onEnregistre,
    })
    expect(screen.getByText('Modifier le niveau')).toBeTruthy()
    const champLibelle = screen.getByTestId('champ-libelle')
    expect(champLibelle.value).toBe('Licence 1')
    fireEvent.change(champLibelle, { target: { value: 'Licence 1 révisée' } })
    await userEvent.click(screen.getByTestId('form-enregistrer'))

    await waitFor(() => expect(onEnregistre).toHaveBeenCalledWith('Modification enregistrée.'))
    const [chemin, corps] = apiController.findCall('patch', '/scolarite/ref/niveaux/7/')
    expect(chemin).toBe('/scolarite/ref/niveaux/7/')
    expect(corps.libelle).toBe('Licence 1 révisée')
  })

  it('affiche le refus du serveur, y compris par champ, sans fermer la boîte', async () => {
    // Refus serveur simulé sur l'écriture seule : la lecture (GET) reste
    // servie par la route programmée en `beforeEach`.
    apiController.api.post.mockRejectedValueOnce({
      response: { status: 400, data: { code: ['Ce code existe déjà.'] } },
    })
    const onFermer = vi.fn()
    monter({ onFermer })
    await userEvent.type(screen.getByTestId('champ-code'), 'L1')
    await userEvent.type(screen.getByTestId('champ-libelle'), 'Doublon')
    await userEvent.selectOptions(screen.getByTestId('champ-cycle'), 'LICENCE')
    await userEvent.type(screen.getByTestId('champ-ordre'), '1')
    await userEvent.click(screen.getByTestId('form-enregistrer'))

    await waitFor(() => expect(screen.getByTestId('form-erreur').textContent)
      .toMatch(/Ce code existe déjà/))
    // L'erreur est aussi rattachée au champ fautif (accessibilité + correction).
    const champCode = screen.getByTestId('champ-code')
    expect(champCode.getAttribute('aria-invalid')).toBe('true')
    expect(screen.getByText('Ce code existe déjà.')).toBeTruthy()
    expect(onFermer).not.toHaveBeenCalled()
  })

  it('se ferme par le bouton Annuler et par la touche Échap', async () => {
    const onFermer = vi.fn()
    monter({ onFermer })
    await userEvent.click(screen.getByRole('button', { name: 'Annuler' }))
    await userEvent.keyboard('{Escape}')
    expect(onFermer).toHaveBeenCalledTimes(2)
  })

  it('n’affiche que les champs réellement déclarés', () => {
    monter()
    const libelles = [...document.querySelectorAll('label.form-label')].map((l) => l.textContent)
    expect(libelles).toHaveLength(FORMULAIRE.champs.length)
  })
})
