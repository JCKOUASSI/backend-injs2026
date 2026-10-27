/**
 * Tests de la saisie des notes d'un module (NotesModule, LOT 14) — chaînon
 * entre la pédagogie (LOT 11) et la délibération du jury (LOT 12).
 *
 * On vérifie par l'extérieur (aucune modification de la page) :
 * - chargement module + grille (colonnes, notes pré-remplies, critères,
 *   mention/moyenne/admission calculés, « saisi par ») ;
 * - recherche/filtre des étudiants ;
 * - saisie en direct (mention normalisée /20, moyenne, signalement de
 *   modifications non sauvegardées, validation de plage) ;
 * - enregistrement en bloc (payload `{ notes, syntheses }`, mention calculée,
 *   réponses partiellement en erreur / échec) ;
 * - ajout/suppression d'une colonne de notes ;
 * - génération des fiches PDF (module / étudiant, garde-fou en cas de saisie
 *   non enregistrée) ;
 * - état vide et échec de chargement (ce dernier confirme, en régression
 *   muette §10.10, qu'aucune requête n'est relancée par un toast d'erreur).
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { screen, act, within, fireEvent } from '@testing-library/react'

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

import apiMock, { apiController } from '@/test/utils/mockApi'
import { renderWithProviders } from '@/test/utils/renderWithProviders'
import { flushPromises } from '@/test/utils/async'
import { makeUser } from '@/test/utils/factories'
import NotesModule from '@/pages/NotesModule'

const F = 10
const M = 77
const modulePath = `/formations/${F}/modules/${M}/`
const notesPath = `/formations/${F}/modules/${M}/notes/`
const bulkPath = `${notesPath}bulk/`
const colonnesPath = `${notesPath}colonnes/`

const COLONNES = [
  { id: 1, libelle: 'CC1', note_max: 20 },
  { id: 2, libelle: 'Examen', note_max: 20 },
]
const ROWS = [
  {
    participant_id: 101, nom: 'Koné', prenom: 'Awa', matricule: 'MAT-001', grade: 'L1',
    observations: '', taux_presence: 90, heures_prevues: 20, heures_presence: 18,
    moyenne: '15.00', mention: 'BIEN', saisie_par: 'M. Formateur', updated_at: '2026-09-01',
    notes: { 1: { note: 14 }, 2: { note: 16 } },
  },
  {
    participant_id: 102, nom: 'Diop', prenom: 'Karim', matricule: 'MAT-002', grade: 'L1',
    observations: '', taux_presence: 70, heures_prevues: 20, heures_presence: 14,
    moyenne: '9.00', mention: 'INSUFFISANT', saisie_par: null, updated_at: null,
    notes: { 1: { note: 8 }, 2: { note: 10 } },
  },
  {
    participant_id: 103, nom: 'Bamba', prenom: 'Fatou', matricule: 'MAT-003', grade: null,
    observations: '', taux_presence: null, heures_prevues: 0, heures_presence: 0,
    moyenne: null, mention: '', saisie_par: null, updated_at: null, notes: {},
  },
]
const CRITERES = { seuil_admission: 12, taux_presence_min: 80 }

// Réponse du GET notes pilotable par test ; compteur d'échecs (régression §10.10).
let notesData = { colonnes: COLONNES, rows: ROWS, criteres: CRITERES }
let notesFailures = 0
const withNotes = (partial) => { notesData = { colonnes: COLONNES, rows: ROWS, criteres: CRITERES, ...partial } }
const failNotesTimes = (n) => { notesFailures = n }

const setupRoutes = () => {
  apiController.setRoute(modulePath, () => ({ id: M, intitule: 'LSF Niveau 1 — Module A1', formation: F }))
  apiController.setRoute(notesPath, () => {
    if (notesFailures > 0) {
      notesFailures -= 1
      // eslint-disable-next-line no-throw-literal
      throw { response: { data: { detail: 'Grille indisponible.' } } }
    }
    return notesData
  })
}

const mount = () => {
  const me = makeUser('ADMIN', { username: 'admin' })
  apiController.setMe(me)
  return renderWithProviders(<NotesModule />, {
    authUser: me,
    routePattern: '/formations/:formationId/modules/:moduleId/notes',
    initialEntries: [`/formations/${F}/modules/${M}/notes`],
  })
}
const settle = async (n = 6) => { await act(async () => { await flushPromises(n) }) }
const gets = (path) => apiMock.get.mock.calls.filter(([p]) => p === path)
const posts = (path) => apiMock.post.mock.calls.filter(([p]) => p === path)
const bulkCall = () => posts(bulkPath).at(-1)?.[1]
const blobCalls = () => apiMock.getBlob.mock.calls.map((c) => c[0])
const rowOf = (matricule) => screen.getByText(matricule).closest('tr')
const noteInputs = (matricule) => within(rowOf(matricule)).getAllByRole('spinbutton')
const obsInput = (matricule) => within(rowOf(matricule)).getByPlaceholderText('Observations…')

beforeEach(() => {
  apiController.reset()
  window.localStorage.clear()
  notesData = { colonnes: COLONNES, rows: ROWS, criteres: CRITERES }
  notesFailures = 0
  setupRoutes()
})

describe('NotesModule — chargement et rendu de la grille', () => {
  it('affiche le module, les critères, les colonnes et les notes pré-remplies', async () => {
    mount()
    expect(await screen.findByText(/LSF Niveau 1/)).toBeInTheDocument()

    // Synthèse d'en-tête.
    expect(screen.getByText(/3 étudiant/)).toBeInTheDocument()
    expect(screen.getByText(/2 avec note/)).toBeInTheDocument()
    expect(screen.getByText(/2 colonnes/)).toBeInTheDocument()
    expect(screen.getByText(/Admis si moyenne/)).toHaveTextContent('12/20')
    expect(screen.getByText(/Admis si moyenne/)).toHaveTextContent('80%')
    // (14+16+8+10)/4 = 12,00.
    expect(screen.getByText('12.00/20')).toBeInTheDocument()

    // Colonnes (libellé + barème) et 6 champs de note (3 lignes × 2 colonnes).
    expect(screen.getByText('CC1')).toBeInTheDocument()
    expect(screen.getAllByText('/ 20').length).toBeGreaterThanOrEqual(2)
    expect(screen.getAllByRole('spinbutton')).toHaveLength(6)

    // Notes serveur pré-remplies, mention/moyenne calculées, décision d'admission.
    expect(noteInputs('MAT-001').map((i) => i.value)).toEqual(['14', '16'])
    expect(within(rowOf('MAT-001')).getByText('Bien')).toBeInTheDocument()
    expect(within(rowOf('MAT-001')).getByText('15.00')).toBeInTheDocument()
    expect(within(rowOf('MAT-001')).getByText(/Oui/)).toBeInTheDocument() // moy 15 ≥ 12, présence 90 ≥ 80
    expect(within(rowOf('MAT-001')).getByText('M. Formateur')).toBeInTheDocument()

    // Karim : moyenne insuffisante ET présence sous le seuil → Non.
    expect(within(rowOf('MAT-002')).getByText('Insuffisant')).toBeInTheDocument()
    expect(within(rowOf('MAT-002')).getByText(/Non/)).toBeInTheDocument()

    // Fatou sans note ni présence : moy/admission/mention en tiret.
    expect(noteInputs('MAT-003').map((i) => i.value)).toEqual(['', ''])
    expect(within(rowOf('MAT-003')).getAllByText('—').length).toBeGreaterThanOrEqual(2)
  })

  it('filtre les lignes par recherche (nom, prénom, matricule, grade)', async () => {
    mount()
    await screen.findByText('MAT-001')

    fireEvent.change(screen.getByPlaceholderText(/rechercher par nom, matricule/i), {
      target: { value: 'Diop' },
    })
    expect(screen.getByText('MAT-002')).toBeInTheDocument()
    expect(screen.queryByText('MAT-001')).not.toBeInTheDocument()
    expect(screen.queryByText('MAT-003')).not.toBeInTheDocument()
    // Une seule ligne visible → 2 champs de note.
    expect(screen.getAllByRole('spinbutton')).toHaveLength(2)

    fireEvent.change(screen.getByPlaceholderText(/rechercher par nom, matricule/i), {
      target: { value: 'L1' },
    })
    expect(screen.getAllByRole('spinbutton')).toHaveLength(4) // Awa + Karim sont en grade L1
  })

  it("affiche l'état vide quand aucun étudiant n'est inscrit", async () => {
    withNotes({ rows: [] })
    mount()
    expect(await screen.findByText(/aucun étudiant inscrit à ce module/i)).toBeInTheDocument()
    expect(screen.getByText(/0 étudiant/)).toBeInTheDocument()
    expect(screen.queryAllByRole('spinbutton')).toHaveLength(0)
    // L'impression de la fiche du module est désactivée sans étudiant.
    expect(screen.getByRole('button', { name: 'Imprimer la fiche' })).toBeDisabled()
  })

  it("n'émet qu'une seule requête (et un seul toast) si le chargement échoue (régression §10.10)", async () => {
    failNotesTimes(3) // 3 échecs programmés ; un écran sain n'en consomme qu'un.
    mount()
    expect(await screen.findByText('Erreur lors du chargement')).toBeInTheDocument()
    await settle()

    expect(gets(notesPath)).toHaveLength(1)
    expect(gets(modulePath)).toHaveLength(1)
    expect(screen.getAllByText('Erreur lors du chargement')).toHaveLength(1)
  })
})

describe('NotesModule — saisie en direct', () => {
  it('recalcule mention et moyenne, et signale des modifications non sauvegardées', async () => {
    mount()
    await screen.findByText('MAT-003')

    // Au départ rien n'est modifié : bouton global désactivé, pas de bandeau.
    expect(screen.getByRole('button', { name: /enregistrer tout/i })).toBeDisabled()
    expect(screen.queryByText('Modifications non sauvegardées')).not.toBeInTheDocument()

    const [cc1, examen] = noteInputs('MAT-003')
    fireEvent.change(cc1, { target: { value: '18' } })
    fireEvent.change(examen, { target: { value: '18' } })

    // Moyenne 18/20 → mention « Très bien » (≥ 16).
    expect(within(rowOf('MAT-003')).getByText('Très bien')).toBeInTheDocument()
    expect(within(rowOf('MAT-003')).getByText('18.00')).toBeInTheDocument()

    // La saisie est marquée non sauvegardée et l'enregistrement se débloque.
    expect(screen.getByText('Modifications non sauvegardées')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /enregistrer tout/i })).toBeEnabled()
  })

  it('signale une note hors plage (0–20)', async () => {
    mount()
    await screen.findByText('MAT-003')

    const [cc1] = noteInputs('MAT-003')
    fireEvent.change(cc1, { target: { value: '25' } })

    expect(within(rowOf('MAT-003')).getByText('0–20')).toBeInTheDocument()
    // Une note invalide n'est pas sauvegardée tant que corrigée : on peut encore
    // saisir, mais le champ est signalé (aucune incidence sur les autres lignes).
    expect(within(rowOf('MAT-001')).queryByText('0–20')).not.toBeInTheDocument()
  })

  it('la touche Entrée fait passer la saisie au champ suivant (ligne puis colonne)', async () => {
    mount()
    await screen.findByText('MAT-003')

    const awa = noteInputs('MAT-001')
    const karim = noteInputs('MAT-002')
    const fatou = noteInputs('MAT-003')

    // Sur une colonne non terminale : Entrée passe à la même colonne du participant suivant.
    fireEvent.keyDown(awa[0], { key: 'Enter' })
    expect(karim[0]).toHaveFocus()

    // Dernière ligne, première colonne : Entrée passe à la colonne suivante du même participant.
    fireEvent.keyDown(fatou[0], { key: 'Enter' })
    expect(fatou[1]).toHaveFocus()
  })

  it('conserve une observation par étudiant dans le brouillon', async () => {
    mount()
    await screen.findByText('MAT-003')
    fireEvent.change(obsInput('MAT-003'), { target: { value: 'Absence justifiée au CC1' } })
    expect(obsInput('MAT-003')).toHaveValue('Absence justifiée au CC1')
    expect(screen.getByText('Modifications non sauvegardées')).toBeInTheDocument()
  })
})

describe('NotesModule — enregistrement en bloc', () => {
  it('construit le payload notes + synthèses (mention calculée), notifie et recharge', async () => {
    apiController.setRoute(bulkPath, () => ({ saved: 5 }))
    mount()
    await screen.findByText('MAT-003')

    // On complète la ligne de Fatou (sans note jusque-là) + une observation.
    const [cc1] = noteInputs('MAT-003')
    fireEvent.change(cc1, { target: { value: '12' } })
    fireEvent.change(obsInput('MAT-003'), { target: { value: 'Très bon travail' } })

    fireEvent.click(screen.getByRole('button', { name: /enregistrer tout/i }))
    expect(await screen.findByText('5 enregistrement(s) sauvegardé(s)')).toBeInTheDocument()

    const body = bulkCall()
    expect(body.notes).toEqual([
      { participant_id: 101, colonne_id: 1, note: 14 },
      { participant_id: 101, colonne_id: 2, note: 16 },
      { participant_id: 102, colonne_id: 1, note: 8 },
      { participant_id: 102, colonne_id: 2, note: 10 },
      { participant_id: 103, colonne_id: 1, note: 12 }, // colonne 2 vide exclue
    ])
    // Une synthèse par ligne qui a au moins une note/observation ; la mention
    // est déduite de la moyenne normalisée des notes présentes.
    expect(body.syntheses).toHaveLength(3)
    expect(body.syntheses).toContainEqual({ participant_id: 101, mention: 'BIEN', observations: '' })
    expect(body.syntheses).toContainEqual({ participant_id: 102, mention: 'INSUFFISANT', observations: '' })
    expect(body.syntheses).toContainEqual({
      participant_id: 103, mention: 'ASSEZ_BIEN', observations: 'Très bon travail',
    })

    // La grille est rechargée et le bandeau de modifications disparaît.
    expect(gets(notesPath).length).toBeGreaterThan(1)
    expect(screen.queryByText('Modifications non sauvegardées')).not.toBeInTheDocument()
  })

  it('notifie en avertissement quand le serveur renvoie des erreurs partielles', async () => {
    apiController.setRoute(bulkPath, () => ({ saved: 3, errors: [{ participant_id: 102 }] }))
    mount()
    await screen.findByText('MAT-003')
    fireEvent.change(noteInputs('MAT-003')[0], { target: { value: '12' } })

    fireEvent.click(screen.getByRole('button', { name: /enregistrer tout/i }))
    expect(await screen.findByText('3 enregistrement(s), 1 erreur(s)')).toBeInTheDocument()
  })

  it('affiche une erreur et conserve la saisie si la sauvegarde échoue', async () => {
    apiController.setRoute(bulkPath, () => {
      // eslint-disable-next-line no-throw-literal
      throw { response: { status: 500 } }
    })
    mount()
    await screen.findByText('MAT-003')
    fireEvent.change(noteInputs('MAT-003')[0], { target: { value: '12' } })

    fireEvent.click(screen.getByRole('button', { name: /enregistrer tout/i }))
    expect(await screen.findByText('Erreur lors de la sauvegarde')).toBeInTheDocument()
    // Pas de perte : la saisie reste marquée comme non sauvegardée.
    expect(screen.getByText('Modifications non sauvegardées')).toBeInTheDocument()
  })
})

describe('NotesModule — colonnes dynamiques', () => {
  it("refuse une colonne sans intitulé (pas d'appel API)", async () => {
    mount()
    await screen.findByText('MAT-001')

    fireEvent.click(screen.getByRole('button', { name: /ajouter une colonne/i }))
    fireEvent.click(screen.getByRole('button', { name: 'Ajouter' }))

    expect(await screen.findByText('Saisissez un intitulé pour la colonne')).toBeInTheDocument()
    expect(posts(colonnesPath)).toHaveLength(0)
  })

  it('ajoute une colonne (POST) et ouvre un champ de saisie par étudiant', async () => {
    apiController.setRoute(colonnesPath, () => ({ id: 3, libelle: 'Projet', note_max: 20 }))
    mount()
    await screen.findByText('MAT-001')

    fireEvent.click(screen.getByRole('button', { name: /ajouter une colonne/i }))
    fireEvent.change(screen.getByPlaceholderText(/examen final, CC2/i), {
      target: { value: 'Projet' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Ajouter' }))

    expect(await screen.findByText('Colonne ajoutée')).toBeInTheDocument()
    expect(posts(colonnesPath)).toEqual([[colonnesPath, { libelle: 'Projet', note_max: 20 }]])
    expect(screen.getByText('Projet')).toBeInTheDocument()
    expect(screen.getAllByRole('spinbutton')).toHaveLength(9) // 3 lignes × 3 colonnes
  })

  it('supprime une colonne après confirmation (DELETE) et recharge, mais pas si annulé', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    mount()
    await screen.findByText('MAT-001')
    // Avec 2 colonnes, un bouton de suppression par colonne.
    expect(screen.getAllByRole('button', { name: 'Supprimer cette colonne' })).toHaveLength(2)

    fireEvent.click(screen.getAllByRole('button', { name: 'Supprimer cette colonne' })[0])
    expect(apiMock.delete.mock.calls).toHaveLength(0)

    window.confirm.mockReturnValue(true)
    fireEvent.click(screen.getAllByRole('button', { name: 'Supprimer cette colonne' })[0])
    expect(await screen.findByText('Colonne supprimée')).toBeInTheDocument()
    expect(apiMock.delete.mock.calls[0][0]).toBe(`${colonnesPath}1/`)
  })

  it("n'offre pas la suppression quand il n'y a qu'une seule colonne", async () => {
    withNotes({ colonnes: [{ id: 1, libelle: 'CC1', note_max: 20 }] })
    mount()
    await screen.findByText('MAT-001')
    expect(screen.queryAllByRole('button', { name: 'Supprimer cette colonne' })).toHaveLength(0)
  })
})

describe('NotesModule — fiches PDF', () => {
  beforeEach(() => {
    // jsdom ne sait pas créer/télécharger un Blob URL : on remplace les API.
    URL.createObjectURL = vi.fn(() => 'blob:fiche')
    URL.revokeObjectURL = vi.fn()
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  })

  it('génère la fiche du module (tous les étudiants)', async () => {
    mount()
    await screen.findByText('MAT-001')
    fireEvent.click(screen.getByRole('button', { name: 'Imprimer la fiche' }))
    await settle()
    expect(blobCalls()).toContain(`${notesPath}fiche/pdf/`)
  })

  it('génère la fiche individuelle d’un étudiant', async () => {
    mount()
    await screen.findByText('MAT-001')
    fireEvent.click(within(rowOf('MAT-001')).getByRole('button', {
      name: /imprimer la fiche de notes de Koné Awa/i,
    }))
    await settle()
    expect(blobCalls()).toContain(`${notesPath}fiche/101/pdf/`)
  })

  it('demande confirmation si des notes ne sont pas enregistrées, et annule proprement', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    mount()
    await screen.findByText('MAT-003')
    fireEvent.change(noteInputs('MAT-003')[0], { target: { value: '18' } }) // rend dirty

    // Annulation : aucune génération.
    fireEvent.click(screen.getByRole('button', { name: 'Imprimer la fiche' }))
    expect(window.confirm).toHaveBeenCalledTimes(1)
    await settle()
    expect(blobCalls()).toHaveLength(0)

    // Confirmation : la génération a lieu.
    window.confirm.mockReturnValue(true)
    fireEvent.click(screen.getByRole('button', { name: 'Imprimer la fiche' }))
    await settle()
    expect(blobCalls()).toContain(`${notesPath}fiche/pdf/`)
  })

  it('notifie une erreur de génération de fiche', async () => {
    apiMock.getBlob.mockRejectedValueOnce({ response: { data: { detail: 'PDF indisponible' } } })
    mount()
    await screen.findByText('MAT-001')
    fireEvent.click(screen.getByRole('button', { name: 'Imprimer la fiche' }))
    expect(await screen.findByText('PDF indisponible')).toBeInTheDocument()
  })
})

describe('NotesModule — navigation', () => {
  it('propose les liens vers les décisions et le module', async () => {
    mount()
    await screen.findByText('MAT-001')
    expect(screen.getByRole('link', { name: /décisions/i }))
      .toHaveAttribute('href', `/formations/${F}/decisions`)
    expect(screen.getByRole('link', { name: /retour au module/i }))
      .toHaveAttribute('href', `/formations/${F}/modules/${M}`)
  })
})
