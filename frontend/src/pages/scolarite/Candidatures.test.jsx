/**
 * Tests de la page Candidatures d'admission (LOT 9) — un écran qui écrit.
 * La page passe par les helpers de `services/scolarite.js` :
 *   liste + référentiels en lecture, puis via le panneau « Dossier » des
 *   transitions de statut, la vérification de pièces et l'ouverture
 *   d'admission, et un formulaire de création candidat + candidature.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { screen, act, within, fireEvent, waitFor } from '@testing-library/react'

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

import apiMock, { apiController } from '@/test/utils/mockApi'
import { renderWithProviders } from '@/test/utils/renderWithProviders'
import { flushPromises } from '@/test/utils/async'
import { makeUser } from '@/test/utils/factories'
import Candidatures, {
  MOIS_FR,
  dateFrancaiseVersIso,
  erreurDateNaissance,
  masquerDateFrancaise,
} from '@/pages/scolarite/Candidatures'

const listCalls = () =>
  apiMock.get.mock.calls
    .filter(([p]) => p.split('?')[0] === '/admissions/candidatures/')
    .map(([p, opts]) => ({ path: p, params: opts?.params || {} }))
const posts = (predicate) =>
  apiMock.post.mock.calls
    .filter(([p]) => predicate(p))
    .map(([p, body]) => ({ path: p, body }))

const setupRoutes = () => {
  apiController.setRoute('/scolarite/annee-courante/', () => ({
    annee: { id: 1, libelle: '2025-2026' },
  }))
  apiController.setRoute('/formations/ref/formations/', () => [
    { id: 10, intitule: 'L1 Langue des signes' },
  ])
  apiController.setRoute('/scolarite/ref/niveaux/', () => [
    { id: 2, code: 'N1', libelle: 'Niveau 1' },
  ])
  apiController.setRoute('/admissions/candidatures/', () => [
    { id: 5, numero: 'C-005', candidat: 'Awa Koné', ref_formation: 'L1 LSF', niveau: 'N1', statut: 'SOUMISE', statut_libelle: 'Soumise', pieces_validees: 1, pieces_obligatoires: 3, taux_completude: 33 },
    { id: 6, numero: 'C-006', candidat: 'Karim Diop', ref_formation: 'L1 LSF', niveau: 'N1', statut: 'ADMISSIBLE', statut_libelle: 'Admissible', pieces_validees: 3, pieces_obligatoires: 3, taux_completude: 100 },
  ])
  apiController.setRoute(/\/admissions\/candidatures\/\d+\/$/, (path) => {
    const id = Number(path.match(/(\d+)/)[1])
    if (id === 6) {
      return {
        id, numero: 'C-006', candidat: 'Karim Diop', statut: 'ADMISSIBLE',
        statut_libelle: 'Admissible', ref_formation: 'L1 LSF', niveau: 'N1',
        annee_academique: '2025-2026', transitions_possibles: [],
        pieces_validees: 3, pieces_obligatoires: 3, taux_completude: 100,
      }
    }
    return {
      id, numero: 'C-005', candidat: 'Awa Koné', statut: 'SOUMISE',
      statut_libelle: 'Soumise', ref_formation: 'L1 LSF', niveau: 'N1',
      annee_academique: '2025-2026',
      transitions_possibles: ['EN_ATTENTE_DE_VERIFICATION', 'ANNULE'],
      pieces_validees: 1, pieces_obligatoires: 3, taux_completude: 33,
    }
  })
  apiController.setRoute(/\/admissions\/candidatures\/\d+\/pieces\/$/, () => ({
    pieces: [
      { id: 51, type_piece: 'CNI', statut: 'FOURNIE', statut_libelle: 'Fournie', a_fichier: true, obligatoire: true },
      { id: 52, type_piece: 'Diplôme', statut: 'MANQUANTE', statut_libelle: 'Manquante', a_fichier: false, obligatoire: true },
    ],
  }))
  apiController.setRoute('/admissions/candidats/', () => ({ id: 99 }))
}

const mount = () => {
  const me = makeUser('ADMIN', { username: 'admin' })
  apiController.setMe(me)
  return renderWithProviders(<Candidatures />, {
    authUser: me,
    routePattern: '/scolarite/candidatures',
    initialEntries: ['/scolarite/candidatures'],
  })
}
/* Panneau de dépôt ouvert : le titre porte le formulaire et sert d'ancre. */
const formOuvert = () => {
  const titre = screen.getByRole('heading', { level: 2, name: /nouvelle candidature/i })
  return titre.closest('.cand-panel')
}
const settle = async (n = 5) => {
  await act(async () => { await flushPromises(n) })
}

const rowOf = (numero) => screen.getByText(numero).closest('tr')
/* Le panneau « Dossier » s'ouvre par le bouton d'action de la ligne ; son
   libellé accessible nomme le dossier concerné. */
const ouvrirDossier = (numero) => {
  const bouton = within(rowOf(numero)).getByRole('button', { name: /ouvrir le dossier/i })
  fireEvent.click(bouton)
}

beforeEach(() => {
  apiController.reset()
  window.localStorage.clear()
  setupRoutes()
})

describe('pages/scolarite/Candidatures — liste et filtres', () => {
  it('charge les candidatures et les affiche avec leur badge de statut', async () => {
    mount()
    expect(await screen.findByText('C-005')).toBeInTheDocument()
    expect(screen.getByText('Awa Koné')).toBeInTheDocument()
    expect(screen.getByText('C-006')).toBeInTheDocument()
    expect(within(rowOf('C-006')).getByText('Admissible')).toBeInTheDocument()
    expect(screen.getByText(/année 2025-2026/i)).toBeInTheDocument()
  })

  it('recherche et filtre par statut en passant les paramètres au service', async () => {
    mount()
    await screen.findByText('C-005')

    fireEvent.change(screen.getByPlaceholderText(/rechercher un numéro/i), { target: { value: 'Koné' } })
    await settle()
    expect(listCalls().at(-1).params).toMatchObject({ q: 'Koné' })

    fireEvent.change(screen.getByDisplayValue('Tous les statuts'), { target: { value: 'SOUMISE' } })
    await settle()
    expect(listCalls().at(-1).params).toMatchObject({ statut: 'SOUMISE' })
  })
})

describe('pages/scolarite/Candidatures — panneau Dossier (écritures)', () => {
  it('applique une transition de statut puis recharge et notifie', async () => {
    mount()
    await screen.findByText('C-005')
    ouvrirDossier('C-005')

    const panel = await screen.findByText('Pièces justificatives')
    expect(panel).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'En attente de vérification' }))
    await settle()

    const t = posts((p) => p.includes('/transition/'))
    expect(t).toHaveLength(1)
    expect(t[0].path).toBe('/admissions/candidatures/5/transition/')
    expect(t[0].body).toEqual({ statut: 'EN_ATTENTE_DE_VERIFICATION' })
    expect(await screen.findByText(/statut mis à jour/i)).toBeInTheDocument()
  })

  it('valide une pièce fournie (POST verifier) ; le bouton reste désactivé sans fichier', async () => {
    mount()
    await screen.findByText('C-005')
    ouvrirDossier('C-005')
    await screen.findByText('CNI')

    const pieceRow = screen.getByText('CNI').closest('tr')
    fireEvent.click(within(pieceRow).getByRole('button', { name: 'Valider la pièce' }))
    await settle()

    const v = posts((p) => p.includes('/verifier/'))
    expect(v).toHaveLength(1)
    expect(v[0].path).toBe('/admissions/pieces/51/verifier/')
    expect(v[0].body).toEqual({ statut: 'VALIDEE' })

    // La pièce sans fichier (Diplôme) ne peut pas être validée.
    const missingRow = screen.getByText('Diplôme').closest('tr')
    expect(within(missingRow).getByRole('button', { name: 'Valider la pièce' })).toBeDisabled()
    expect(within(missingRow).getByRole('button', { name: 'Refuser la pièce' })).toBeDisabled()
  })

  it('ouvre une admission pour une candidature admissible', async () => {
    mount()
    await screen.findByText('C-006')
    ouvrirDossier('C-006')
    await screen.findByText('Suite du parcours')

    fireEvent.click(screen.getByRole('button', { name: /ouvrir une admission/i }))
    await settle()

    const a = posts((p) => p === '/admissions/admissions/')
    expect(a).toHaveLength(1)
    expect(a[0].body).toEqual({ candidature_id: 6 })
    expect(await screen.findByText(/admission ouverte/i)).toBeInTheDocument()
  })

  it('affiche le message serveur si la transition est refusée', async () => {
    apiController.setRoute(/\/transition\//, () => {
      // eslint-disable-next-line no-throw-literal
      throw { response: { data: { error: 'Transition métier impossible.' } } }
    })
    mount()
    await screen.findByText('C-005')
    ouvrirDossier('C-005')
    await screen.findByText('Pièces justificatives')

    fireEvent.click(screen.getByRole('button', { name: 'En attente de vérification' }))
    await settle()

    expect(await screen.findByText('Transition métier impossible.')).toBeInTheDocument()
  })

  it('dépose un fichier pour une pièce (POST FormData multipart)', async () => {
    mount()
    await screen.findByText('C-005')
    ouvrirDossier('C-005')
    await screen.findByText('CNI')

    const input = screen
      .getByText('CNI')
      .closest('tr')
      .querySelector('input[type="file"]')
    expect(input).not.toBeNull()
    fireEvent.change(input, {
      target: { files: [new File(['contenu'], 'cni.pdf', { type: 'application/pdf' })] },
    })
    await settle()

    const depots = posts((p) => p.includes('/deposer/'))
    expect(depots).toHaveLength(1)
    expect(depots[0].path).toBe('/admissions/pieces/51/deposer/')
    expect(depots[0].body).toBeInstanceOf(FormData)
    expect(await screen.findByText('CNI déposée')).toBeInTheDocument()
  })
})

describe('pages/scolarite/Candidatures — création', () => {
  it('crée le candidat puis sa candidature avec l’année courante', async () => {
    mount()
    await screen.findByText('C-005')

    fireEvent.click(screen.getByRole('button', { name: /nouvelle candidature/i }))
    const card = formOuvert()

    fireEvent.change(within(card).getByLabelText('Nom'), { target: { value: 'Traoré' } })
    fireEvent.change(within(card).getByLabelText('Prénoms'), { target: { value: 'Mariam' } })
    fireEvent.change(within(card).getByLabelText('Formation demandée'), { target: { value: '10' } })
    fireEvent.change(within(card).getByLabelText('Niveau demandé'), { target: { value: '2' } })

    const enregistrer = within(card).getByRole('button', { name: /enregistrer la candidature/i })
    await waitFor(() => expect(enregistrer).not.toBeDisabled())
    fireEvent.click(enregistrer)
    await settle()

    const candidats = posts((p) => p === '/admissions/candidats/')
    expect(candidats).toHaveLength(1)
    expect(candidats[0].body).toMatchObject({ nom: 'Traoré', prenom: 'Mariam' })

    const dossiers = posts((p) => p === '/admissions/candidatures/')
    expect(dossiers).toHaveLength(1)
    expect(dossiers[0].body).toMatchObject({
      candidat_id: 99,
      annee_academique_id: 1,
      ref_formation_id: '10',
      niveau_id: '2',
    })
    expect(await screen.findByText('Candidature enregistrée')).toBeInTheDocument()
  })

  it('affiche l’erreur serveur dans le formulaire sans créer de candidature', async () => {
    // On réenregistre la route en échec AVANT les routes de setup : la première
    // correspondance l'emporte dans le mock.
    apiController.reset()
    apiController.setRoute('/admissions/candidats/', () => {
      // eslint-disable-next-line no-throw-literal
      throw { response: { data: { nom: 'Ce champ est obligatoire.' } } }
    })
    setupRoutes()
    mount()
    await screen.findByText('C-005')

    fireEvent.click(screen.getByRole('button', { name: /nouvelle candidature/i }))
    const card = formOuvert()

    fireEvent.change(within(card).getByLabelText('Nom'), { target: { value: 'Traoré' } })
    fireEvent.change(within(card).getByLabelText('Prénoms'), { target: { value: 'Mariam' } })
    fireEvent.change(within(card).getByLabelText('Formation demandée'), { target: { value: '10' } })
    fireEvent.change(within(card).getByLabelText('Niveau demandé'), { target: { value: '2' } })
    fireEvent.click(within(card).getByRole('button', { name: /enregistrer la candidature/i }))
    await settle()

    expect(await within(card).findByText(/nom : ce champ est obligatoire/i)).toBeInTheDocument()
    // Aucune candidature n'a été créée (le candidat a échoué).
    expect(posts((p) => p === '/admissions/candidatures/')).toHaveLength(0)
  })
})

describe('pages/scolarite/Candidatures — saisie manuelle de la date de naissance', () => {
  it('masque JJ/MM/AAAA : séparateurs automatiques pendant la frappe', () => {
    expect(masquerDateFrancaise('')).toBe('')
    expect(masquerDateFrancaise('0')).toBe('0')
    expect(masquerDateFrancaise('021')).toBe('02/1')
    expect(masquerDateFrancaise('02112007')).toBe('02/11/2007')
    // Idempotent (collage déjà formaté) et borné à 8 chiffres.
    expect(masquerDateFrancaise('02/11/2007')).toBe('02/11/2007')
    expect(masquerDateFrancaise('02112007999')).toBe('02/11/2007')
    expect(masquerDateFrancaise('02-11-2007')).toBe('02/11/2007')
  })

  it('convertit JJ/MM/AAAA en ISO et refuse les dates inexistantes', () => {
    expect(dateFrancaiseVersIso('02/11/2007')).toBe('2007-11-02')
    expect(dateFrancaiseVersIso('29/02/2024')).toBe('2024-02-29')
    expect(dateFrancaiseVersIso('29/02/2023')).toBeNull()
    expect(dateFrancaiseVersIso('31/02/2007')).toBeNull()
    expect(dateFrancaiseVersIso('2/11/2007')).toBeNull()
    expect(dateFrancaiseVersIso('')).toBeNull()
  })

  it('valide : absente admise, invalide et futur refusés', () => {
    expect(erreurDateNaissance('')).toBe('')
    expect(erreurDateNaissance('14/03/2007')).toBe('')
    expect(erreurDateNaissance('31/02/2007')).toMatch(/invalide/i)
    expect(erreurDateNaissance('14/03/')).toMatch(/invalide/i)
    const demain = new Date(Date.now() + 24 * 3600 * 1000)
    const jj = String(demain.getDate()).padStart(2, '0')
    const mm = String(demain.getMonth() + 1).padStart(2, '0')
    expect(erreurDateNaissance(`${jj}/${mm}/${demain.getFullYear()}`)).toMatch(/futur/i)
  })

  const remplirIdentite = (card) => {
    fireEvent.change(within(card).getByLabelText('Nom'), { target: { value: 'Traoré' } })
    fireEvent.change(within(card).getByLabelText('Prénoms'), { target: { value: 'Mariam' } })
    fireEvent.change(within(card).getByLabelText('Formation demandée'), { target: { value: '10' } })
    fireEvent.change(within(card).getByLabelText('Niveau demandé'), { target: { value: '2' } })
  }

  it('le champ accepte la frappe libre et envoie la date en ISO', async () => {
    mount()
    await screen.findByText('C-005')
    fireEvent.click(screen.getByRole('button', { name: /nouvelle candidature/i }))
    const card = formOuvert()
    remplirIdentite(card)

    const champDate = within(card).getByLabelText('Date de naissance')
    expect(champDate).toHaveAttribute('placeholder', 'JJ/MM/AAAA')
    expect(champDate).toHaveAttribute('inputmode', 'numeric')

    fireEvent.change(champDate, { target: { value: '14032007' } })
    expect(champDate).toHaveValue('14/03/2007')

    fireEvent.click(within(card).getByRole('button', { name: /enregistrer la candidature/i }))
    await settle()

    const candidats = posts((p) => p === '/admissions/candidats/')
    expect(candidats).toHaveLength(1)
    expect(candidats[0].body).toMatchObject({ date_naissance: '2007-03-14' })
    expect(await screen.findByText('Candidature enregistrée')).toBeInTheDocument()
  })

  it('une date inexistante bloque l’enregistrement avec un message clair', async () => {
    mount()
    await screen.findByText('C-005')
    fireEvent.click(screen.getByRole('button', { name: /nouvelle candidature/i }))
    const card = formOuvert()
    remplirIdentite(card)

    fireEvent.change(within(card).getByLabelText('Date de naissance'), {
      target: { value: '31022007' },
    })
    fireEvent.click(within(card).getByRole('button', { name: /enregistrer la candidature/i }))
    await settle()

    expect(await within(card).findByText(/date de naissance invalide/i)).toBeInTheDocument()
    expect(posts((p) => p === '/admissions/candidats/')).toHaveLength(0)
    expect(posts((p) => p === '/admissions/candidatures/')).toHaveLength(0)
  })

  it('sans date saisie, l’enregistrement envoie une valeur vide', async () => {
    mount()
    await screen.findByText('C-005')
    fireEvent.click(screen.getByRole('button', { name: /nouvelle candidature/i }))
    const card = formOuvert()
    remplirIdentite(card)

    fireEvent.click(within(card).getByRole('button', { name: /enregistrer la candidature/i }))
    await settle()

    const candidats = posts((p) => p === '/admissions/candidats/')
    expect(candidats).toHaveLength(1)
    expect(candidats[0].body).toMatchObject({ date_naissance: '' })
  })
})

describe('pages/scolarite/Candidatures — calendrier premium de la date de naissance', () => {
  const ouvrirFormulaire = async () => {
    mount()
    await screen.findByText('C-005')
    fireEvent.click(screen.getByRole('button', { name: /nouvelle candidature/i }))
    return formOuvert()
  }

  const remplir = (card) => {
    fireEvent.change(within(card).getByLabelText('Nom'), { target: { value: 'Traoré' } })
    fireEvent.change(within(card).getByLabelText('Prénoms'), { target: { value: 'Mariam' } })
    fireEvent.change(within(card).getByLabelText('Formation demandée'), { target: { value: '10' } })
    fireEvent.change(within(card).getByLabelText('Niveau demandé'), { target: { value: '2' } })
  }

  const ouvrirCalendrier = async (card) => {
    fireEvent.click(within(card).getByRole('button', { name: /ouvrir le calendrier/i }))
    return screen.findByRole('dialog', { name: /choisir une date de naissance/i })
  }

  it('s’ouvre une vingtaine d’années en arrière quand le champ est vide', async () => {
    const card = await ouvrirFormulaire()
    const dialogue = await ouvrirCalendrier(card)
    const maintenant = new Date()
    expect(within(dialogue).getByLabelText('Année affichée'))
      .toHaveValue(String(maintenant.getFullYear() - 20))
    expect(within(dialogue).getByLabelText('Mois affiché'))
      .toHaveValue(String(maintenant.getMonth()))
  })

  it('sélectionne un jour après navigation mois/année et envoie la date en ISO', async () => {
    const card = await ouvrirFormulaire()
    remplir(card)
    const dialogue = await ouvrirCalendrier(card)

    fireEvent.change(within(dialogue).getByLabelText('Mois affiché'), { target: { value: '2' } })
    fireEvent.change(within(dialogue).getByLabelText('Année affichée'), { target: { value: '2007' } })
    fireEvent.click(within(dialogue).getByRole('button', { name: '14 mars 2007' }))

    expect(within(card).getByLabelText('Date de naissance')).toHaveValue('14/03/2007')
    expect(screen.queryByRole('dialog', { name: /choisir une date de naissance/i }))
      .not.toBeInTheDocument()

    fireEvent.click(within(card).getByRole('button', { name: /enregistrer la candidature/i }))
    await settle()
    const candidats = posts((p) => p === '/admissions/candidats/')
    expect(candidats).toHaveLength(1)
    expect(candidats[0].body).toMatchObject({ date_naissance: '2007-03-14' })
  })

  it('rouvre sur le mois de la date déjà saisie et marque le jour choisi', async () => {
    const card = await ouvrirFormulaire()
    fireEvent.change(within(card).getByLabelText('Date de naissance'), {
      target: { value: '14032007' },
    })
    const dialogue = await ouvrirCalendrier(card)
    expect(within(dialogue).getByLabelText('Mois affiché')).toHaveValue('2')
    expect(within(dialogue).getByLabelText('Année affichée')).toHaveValue('2007')
    expect(within(dialogue).getByRole('button', { name: '14 mars 2007' }))
      .toHaveAttribute('aria-pressed', 'true')
  })

  it('désactive les dates futures', async () => {
    const card = await ouvrirFormulaire()
    const dialogue = await ouvrirCalendrier(card)
    const maintenant = new Date()
    fireEvent.change(within(dialogue).getByLabelText('Mois affiché'), {
      target: { value: String(maintenant.getMonth()) },
    })
    fireEvent.change(within(dialogue).getByLabelText('Année affichée'), {
      target: { value: String(maintenant.getFullYear()) },
    })
    const demain = new Date(Date.now() + 24 * 3600 * 1000)
    const libelle = `${demain.getDate()} ${MOIS_FR[demain.getMonth()]} ${demain.getFullYear()}`
    expect(within(dialogue).getByRole('button', { name: libelle })).toBeDisabled()
  })

  it('Échap ferme le calendrier ; Effacer vide le champ', async () => {
    const card = await ouvrirFormulaire()
    const champDate = within(card).getByLabelText('Date de naissance')
    fireEvent.change(champDate, { target: { value: '14032007' } })

    let dialogue = await ouvrirCalendrier(card)
    fireEvent.keyDown(dialogue, { key: 'Escape' })
    expect(screen.queryByRole('dialog', { name: /choisir une date de naissance/i }))
      .not.toBeInTheDocument()
    expect(champDate).toHaveValue('14/03/2007')

    dialogue = await ouvrirCalendrier(card)
    fireEvent.click(within(dialogue).getByRole('button', { name: /effacer/i }))
    expect(champDate).toHaveValue('')
    expect(screen.queryByRole('dialog', { name: /choisir une date de naissance/i }))
      .not.toBeInTheDocument()
  })
})

describe('pages/scolarite/Candidatures — chargement explicite de 200 dossiers', () => {
  it('demande page_size=200, lit l’enveloppe paginée et l’annonce dans l’écran', async () => {
    apiController.reset()
    // Route enveloppe déclarée AVANT setupRoutes (premier motif gagnant).
    apiController.setRoute('/admissions/candidatures/', () => ({
      count: 1, total_pages: 1, page: 1, page_size: 200,
      results: [{
        id: 7, numero: 'C-200', candidat: 'Test Deux Cents', ref_formation: 'L1 LSF',
        niveau: 'N1', statut: 'SOUMISE', statut_libelle: 'Soumise',
        pieces_validees: 0, pieces_obligatoires: 2, taux_completude: 0,
      }],
    }))
    setupRoutes()
    mount()
    expect(await screen.findByText('C-200')).toBeInTheDocument()
    expect(listCalls().at(-1).params).toMatchObject({ page_size: 200 })
    expect(screen.getByText(/Chargement explicite : 200 dossiers/)).toBeInTheDocument()
    expect(screen.queryByText(/Affichage limité/)).not.toBeInTheDocument()
  })
})
