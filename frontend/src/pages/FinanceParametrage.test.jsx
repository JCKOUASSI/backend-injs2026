/**
 * LOT 28 — Finance : paramétrage (`pages/FinanceParametrage.jsx`).
 * Tarifs horaires par formation, marge de tolérance et personnalisation des
 * exports (GET/PATCH `/formations/finance/settings/`), habilitations,
 * validation des tarifs et répercussion de la sauvegarde.
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
import FinanceParametrage from '@/pages/FinanceParametrage'

const SETTINGS_PATH = '/formations/finance/settings/'

const moisCourant = () => {
  const n = new Date()
  return `${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, '0')}`
}

/* ------------------------------------------------------------------ */
/* Jeux de données                                                      */
/* ------------------------------------------------------------------ */

// Trois tarifs : deux actifs (dont un non défini), un inactif en fin de
// tableau. Tolérance désactivée mais valeurs mémorisées, exports servis.
const settings = {
  tarifs_formations: [
    { id: 1, intitule: 'Licence LSF Niveau 1', actif: true, prix_heure_realisee: 5000 },
    { id: 2, intitule: 'Master Interprétation', actif: true, prix_heure_realisee: null },
    { id: 3, intitule: 'Cycle archivé 2024', actif: false, prix_heure_realisee: 3000 },
  ],
  tolerance_active: false,
  tolerance_minutes: 45,
  tolerance_pct: 10,
  afficher_montants_exports: true,
  export_titre_document: 'FICHE DE PAIE 2026',
  export_reference_prefix: 'INJ',
  export_entete_ligne1: 'République de Côte d’Ivoire',
  export_entete_ligne2: 'Ministère de la Fonction publique',
  export_organisme: 'INJS Marcory',
  export_adresse: 'Cocody, Riviera Palmeraie',
  export_signataire_nom: 'M. Yao Konan',
  export_signataire_fonction: 'Directeur',
  export_mention_legale: 'NB : volume horaire prévisionnel.',
  export_contacts: 'M. Yao — 07 00 00 00 00',
  export_pied_page_titre: 'DOCUMENT CONFIDENTIEL',
  export_pied_page_texte: 'Texte institutionnel de pied de page.',
  updated_at: '2026-03-04T10:20:00Z',
  updated_by: 'Jean Finance',
}

// Variante avec tarif reçu sous forme de chaîne à virgule (le code de
// parsing accepte le séparateur décimal français).
const settingsVirgule = {
  ...settings,
  tarifs_formations: [
    { id: 1, intitule: 'Licence LSF Niveau 1', actif: true, prix_heure_realisee: '7500,25' },
  ],
}

// Réponse après sauvegarde : tarifs modifiés, tolérance activée, exports
// différents, nouveau méta-audit. L'inactif garde un tarif nul (repli GET
// comme PATCH), tous les champs d'exports sont renvoyés par le serveur.
const savedSettings = {
  tarifs_formations: [
    { id: 1, intitule: 'Licence LSF Niveau 1', actif: true, prix_heure_realisee: 6500 },
    { id: 2, intitule: 'Master Interprétation', actif: true, prix_heure_realisee: 4200 },
    { id: 3, intitule: 'Cycle archivé 2024', actif: false, prix_heure_realisee: null },
  ],
  tolerance_active: true,
  tolerance_minutes: 20,
  tolerance_pct: 8,
  afficher_montants_exports: false,
  export_titre_document: 'FICHE ENREGISTRÉE',
  export_reference_prefix: 'SAV',
  export_entete_ligne1: 'Entête 1 sauvée',
  export_entete_ligne2: 'Entête 2 sauvée',
  export_organisme: 'Organisme sauvé',
  export_adresse: 'Adresse sauvée',
  export_signataire_nom: 'Signataire sauvé',
  export_signataire_fonction: 'Fonction sauvée',
  export_mention_legale: 'Mention sauvée',
  export_contacts: 'Contacts sauvés',
  export_pied_page_titre: 'Titre pied sauvé',
  export_pied_page_texte: 'Texte pied sauvé',
  updated_at: '2026-05-06T09:00:00Z',
  updated_by: 'Marie Sauvegarde',
}

/* ------------------------------------------------------------------ */
/* Helpers                                                              */
/* ------------------------------------------------------------------ */

const settle = async (n = 5) => { await act(async () => { await flushPromises(n) }) }

const mount = (role = 'FINANCE') => {
  const me = makeUser(role, { username: role.toLowerCase() })
  apiController.setMe(me)
  return renderWithProviders(<FinanceParametrage />, {
    authUser: me,
    routePattern: '/finance-parametrage',
    initialEntries: ['/finance-parametrage'],
  })
}

const submitButton = () => document.querySelector('form button[type="submit"]')

const rowFor = (intitule) => screen.getByText(intitule).closest('tr')
const tarifInput = (intitule) => within(rowFor(intitule)).getByRole('spinbutton')

// Les <label> des champs de formulaire ne sont pas reliés par htmlFor
// (hors interrupteurs) : le champ est dans le même bloc que le label.
const fieldByLabel = (text) => {
  const label = screen.getByText(
    (_c, el) => el.tagName === 'LABEL' && el.textContent.trim() === text,
  )
  return label.parentElement.querySelector('input, textarea')
}

const toleranceSwitch = () => screen.getByLabelText(/Activer la marge de tolérance/i)
const montantsSwitch = () => screen.getByLabelText(/Afficher les montants par défaut/i)

const lastPatchBody = () => apiMock.patch.mock.calls.at(-1)[1]

/* ------------------------------------------------------------------ */
/* LOT 28 — chargement, tarifs, navigation                             */
/* ------------------------------------------------------------------ */

describe('pages/FinanceParametrage.jsx — chargement et affichage (LOT 28)', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
    window.sessionStorage.clear()
    apiController.setRoute(SETTINGS_PATH, () => settings)
  })

  it('charge les réglages et affiche titre, sous-titre, navigation sans filtre de période', async () => {
    const { container } = mount()
    expect(container.querySelector('.loading .spinner')).toBeTruthy()
    await settle()

    expect(apiMock.get).toHaveBeenCalledWith(SETTINGS_PATH)
    expect(screen.getByRole('heading', { name: 'Paramétrage Finance', level: 1 })).toBeInTheDocument()
    expect(screen.getByText(/Tarifs horaires et exports/i)).toBeInTheDocument()
    for (const label of ['Tableau de bord', 'Enseignants', 'Encadrants', 'Ajustements']) {
      expect(screen.getByRole('link', { name: new RegExp(label, 'i') })).toBeInTheDocument()
    }
    const actif = screen.getByRole('link', { name: /paramétrage/i })
    expect(actif).toHaveClass('btn-finance-accent')
    // Pas de panneau de période sur cette page.
    expect(document.querySelector('.finance-filter-panel')).toBeNull()
  })

  it('classe les tarifs actifs puis inactifs avec badge, valeurs et colonne appliquée', async () => {
    mount()
    await settle()

    const rows = [...document.querySelectorAll('table.finance-settings-table tbody tr')]
    expect(rows.map((r) => r.textContent)).toHaveLength(3)
    // Ligne inactive en dernier, grisée et badgée.
    const inactiveRow = rowFor('Cycle archivé 2024')
    expect(inactiveRow).toBe(rows[2])
    expect(inactiveRow).toHaveClass('text-muted')
    expect(within(inactiveRow).getByText('Inactif')).toHaveClass('badge')

    // Champs tarif : nombres servis en chaînes, valeur null -> champ vide.
    expect(tarifInput('Licence LSF Niveau 1')).toHaveValue(5000)
    expect(tarifInput('Cycle archivé 2024')).toHaveValue(3000)
    expect(tarifInput('Master Interprétation')).toHaveValue(null)

    // Colonne « Tarif appliqué » (séparateurs de milliers fr-FR) et repli.
    expect(within(rowFor('Licence LSF Niveau 1')).getByText(/5\s?000 FCFA \/ h/)).toBeInTheDocument()
    expect(within(rowFor('Cycle archivé 2024')).getByText(/3\s?000 FCFA \/ h/)).toBeInTheDocument()
    expect(within(rowFor('Master Interprétation')).getByText('Non défini')).toHaveClass('text-warning')
  })

  it("affiche un message quand le référentiel ne contient aucune formation", async () => {
    apiController.reset()
    const me = makeUser('FINANCE', { username: 'finance' })
    apiController.setMe(me)
    apiController.setRoute(SETTINGS_PATH, () => ({ ...settings, tarifs_formations: [] }))
    renderWithProviders(<FinanceParametrage />, {
      authUser: me, routePattern: '/finance-parametrage', initialEntries: ['/finance-parametrage'],
    })
    await settle()
    expect(screen.getByText(/aucune formation dans le référentiel/i)).toBeInTheDocument()
    expect(document.querySelector('table.finance-settings-table')).toBeNull()
  })

  it("révèle les champs de tolérance (valeurs servies) avec le texte d'explication", async () => {
    mount()
    await settle()
    expect(toleranceSwitch()).not.toBeChecked()
    expect(screen.queryByText('Tolérance fixe (minutes)')).toBeNull()

    fireEvent.click(toleranceSwitch())
    expect(toleranceSwitch()).toBeChecked()
    expect(fieldByLabel('Tolérance fixe (minutes)')).toHaveValue(45)
    expect(fieldByLabel('Tolérance relative (%)')).toHaveValue(10)
    expect(screen.getByText(/le seuil appliqué est le plus favorable/i)).toBeInTheDocument()
  })

  it('restitue les réglages des exports servis par le backend', async () => {
    mount()
    await settle()
    expect(montantsSwitch()).toBeChecked()
    expect(fieldByLabel('Titre du document')).toHaveValue('FICHE DE PAIE 2026')
    expect(fieldByLabel('Préfixe référence')).toHaveValue('INJ')
    expect(fieldByLabel('Organisme')).toHaveValue('INJS Marcory')
    expect(fieldByLabel('En-tête ligne 1')).toHaveValue('République de Côte d’Ivoire')
    expect(fieldByLabel('Contacts (fiche récap formateur)')).toHaveValue('M. Yao — 07 00 00 00 00')
  })

  it("affiche le méta-audit de dernière mise à jour (date formatée et auteur)", async () => {
    mount()
    await settle()
    const meta = screen.getByText(/Dernière mise à jour/i)
    expect(meta).toHaveTextContent('04/03/2026')
    expect(meta).toHaveTextContent(/par Jean Finance/)
  })

  it("notifie une erreur de chargement sans rendre le formulaire", async () => {
    apiController.reset()
    const me = makeUser('FINANCE', { username: 'finance' })
    apiController.setMe(me)
    apiController.setRoute(SETTINGS_PATH, () => {
      // eslint-disable-next-line no-throw-literal
      throw { response: { data: { detail: 'Service indisponible' } } }
    })
    renderWithProviders(<FinanceParametrage />, {
      authUser: me, routePattern: '/finance-parametrage', initialEntries: ['/finance-parametrage'],
    })
    expect(await screen.findByText('Impossible de charger les paramètres finance.')).toBeInTheDocument()
    // Le spinner disparaît : la carte reste rendue, vide (aucun tarif).
    await settle()
    expect(document.querySelector('.loading .spinner')).toBeNull()
    expect(document.querySelector('.finance-settings-card')).toBeTruthy()
    expect(screen.getByText(/aucune formation dans le référentiel/i)).toBeInTheDocument()
  })
})

/* ------------------------------------------------------------------ */
/* LOT 28 — habilitations                                              */
/* ------------------------------------------------------------------ */

describe('pages/FinanceParametrage.jsx — habilitations (LOT 28)', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
    window.sessionStorage.clear()
    apiController.setRoute(SETTINGS_PATH, () => settings)
  })

  it("en FINANCE : champs activés et bouton Enregistrer présent", async () => {
    mount('FINANCE')
    await settle()
    expect(screen.queryByText(/consultation seule/i)).toBeNull()
    expect(tarifInput('Licence LSF Niveau 1')).toBeEnabled()
    expect(toleranceSwitch()).toBeEnabled()
    expect(montantsSwitch()).toBeEnabled()
    expect(fieldByLabel('Titre du document')).toBeEnabled()
    expect(submitButton()).toBeEnabled()
  })

  it("hors FINANCE : consultation seule, tout est désactivé et pas de bouton", async () => {
    mount('ENCADRANT')
    await settle()
    expect(screen.getByText(/consultation seule/i)).toBeInTheDocument()
    expect(submitButton()).toBeNull()
    expect(tarifInput('Licence LSF Niveau 1')).toBeDisabled()
    expect(toleranceSwitch()).toBeDisabled()
    expect(montantsSwitch()).toBeDisabled()
    expect(fieldByLabel('Titre du document')).toBeDisabled()
    expect(fieldByLabel('Contacts (fiche récap formateur)')).toBeDisabled()

    // Tenter de soumettre le formulaire n'émet aucun PATCH.
    fireEvent.submit(document.querySelector('form'))
    await settle()
    expect(apiMock.patch).not.toHaveBeenCalled()
  })
})

/* ------------------------------------------------------------------ */
/* LOT 28 — édition et sauvegarde                                      */
/* ------------------------------------------------------------------ */

describe('pages/FinanceParametrage.jsx — édition et sauvegarde (LOT 28)', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
    window.sessionStorage.clear()
    apiController.setRoute(SETTINGS_PATH, (path, body) =>
      body && path === SETTINGS_PATH ? savedSettings : settings,
    )
  })

  it("met à jour la colonne « tarif appliqué » pendant la saisie", async () => {
    mount()
    await settle()
    fireEvent.change(tarifInput('Licence LSF Niveau 1'), { target: { value: '6500' } })
    expect(within(rowFor('Licence LSF Niveau 1')).getByText(/6\s?500 FCFA \/ h/)).toBeInTheDocument()
  })

  it("refuse un tarif négatif : toast détaillé et aucun PATCH", async () => {
    mount()
    await settle()
    fireEvent.change(tarifInput('Licence LSF Niveau 1'), { target: { value: '-5' } })
    // fireEvent.submit contourne la validation native min=0 du navigateur pour
    // exercer la validation métier parsePrix de la page.
    fireEvent.submit(document.querySelector('form'))
    expect(await screen.findByText('Tarif invalide pour « Licence LSF Niveau 1 ».')).toBeInTheDocument()
    expect(apiMock.patch).not.toHaveBeenCalled()
  })

  it("construit le payload complet (tarifs, tolérance, exports) et notifie le succès", async () => {
    mount()
    await settle()
    // Le tarif non défini reste vide -> null ; on modifie le premier tarif.
    fireEvent.change(tarifInput('Licence LSF Niveau 1'), { target: { value: '6500' } })
    fireEvent.change(fieldByLabel('Organisme'), { target: { value: 'INJS Cocody' } })
    fireEvent.click(submitButton())

    await screen.findByText('Paramètres enregistrés')
    expect(apiMock.patch).toHaveBeenCalledTimes(1)
    expect(apiMock.patch.mock.calls[0][0]).toBe(SETTINGS_PATH)
    const body = lastPatchBody()
    expect(body.tarifs_formations).toEqual([
      { id: 1, prix_heure_realisee: 6500 },
      { id: 2, prix_heure_realisee: null },
      { id: 3, prix_heure_realisee: 3000 },
    ])
    expect(body.tolerance_active).toBe(false)
    expect(body.tolerance_minutes).toBe(45)
    expect(body.tolerance_pct).toBe(10)
    expect(body.afficher_montants_exports).toBe(true)
    expect(body.export_titre_document).toBe('FICHE DE PAIE 2026')
    expect(body.export_reference_prefix).toBe('INJ')
    expect(body.export_organisme).toBe('INJS Cocody')
  })

  it("accepte le séparateur décimal virgule reçu du serveur (chaîne)", async () => {
    apiController.reset()
    const me = makeUser('FINANCE', { username: 'finance' })
    apiController.setMe(me)
    apiController.setRoute(SETTINGS_PATH, settingsVirgule)
    renderWithProviders(<FinanceParametrage />, {
      authUser: me, routePattern: '/finance-parametrage', initialEntries: ['/finance-parametrage'],
    })
    await settle()
    fireEvent.click(submitButton())
    await screen.findByText('Paramètres enregistrés')
    expect(lastPatchBody().tarifs_formations).toEqual([
      { id: 1, prix_heure_realisee: 7500.25 },
    ])
  })

  it("coerce les nombres de tolérance en zéro quand les champs sont vidés", async () => {
    mount()
    await settle()
    fireEvent.click(toleranceSwitch())
    fireEvent.change(fieldByLabel('Tolérance fixe (minutes)'), { target: { value: '' } })
    fireEvent.change(fieldByLabel('Tolérance relative (%)'), { target: { value: '' } })
    fireEvent.click(submitButton())
    await screen.findByText('Paramètres enregistrés')
    expect(lastPatchBody().tolerance_active).toBe(true)
    expect(lastPatchBody().tolerance_minutes).toBe(0)
    expect(lastPatchBody().tolerance_pct).toBe(0)
  })

  it("transmet interrupteurs, textes et zones de saisie des exports au PATCH", async () => {
    mount()
    await settle()
    fireEvent.click(montantsSwitch()) // décoché
    fireEvent.change(fieldByLabel('Titre du document'), { target: { value: 'NOUVEAU TITRE' } })
    fireEvent.change(fieldByLabel('Préfixe référence'), { target: { value: 'XYZ' } })
    fireEvent.change(fieldByLabel('Contacts (fiche récap formateur)'), {
      target: { value: 'Ligne contact 1\nLigne contact 2' },
    })
    fireEvent.click(submitButton())
    await screen.findByText('Paramètres enregistrés')
    const body = lastPatchBody()
    expect(body.afficher_montants_exports).toBe(false)
    expect(body.export_titre_document).toBe('NOUVEAU TITRE')
    expect(body.export_reference_prefix).toBe('XYZ')
    expect(body.export_contacts).toBe('Ligne contact 1\nLigne contact 2')
  })

  it("édite et enregistre l'intégralité des champs d'exports (12 champs)", async () => {
    mount()
    await settle()
    const changements = [
      { label: 'Titre du document', key: 'export_titre_document', value: 'TITRE MODIFIÉ' },
      { label: 'Préfixe référence', key: 'export_reference_prefix', value: 'MOD' },
      { label: 'En-tête ligne 1', key: 'export_entete_ligne1', value: 'EN-TETE 1' },
      { label: 'En-tête ligne 2', key: 'export_entete_ligne2', value: 'EN-TETE 2' },
      { label: 'Organisme', key: 'export_organisme', value: 'ORG' },
      { label: 'Signataire — nom', key: 'export_signataire_nom', value: 'NOM SIGNATAIRE' },
      { label: 'Coordonnées en-tête (synthèse globale)', key: 'export_adresse', value: 'ADRESSE SYNTHESE' },
      { label: 'Signataire — fonction', key: 'export_signataire_fonction', value: 'FONCTION SIGNATAIRE' },
      { label: 'Note NB (sous le tableau modules)', key: 'export_mention_legale', value: 'MENTION NB' },
      { label: 'Contacts (fiche récap formateur)', key: 'export_contacts', value: 'CONTACT UN' },
      { label: 'Titre', key: 'export_pied_page_titre', value: 'TITRE PIED' },
      { label: 'Texte institutionnel', key: 'export_pied_page_texte', value: 'TEXTE PIED' },
    ]
    for (const { label, value } of changements) {
      fireEvent.change(fieldByLabel(label), { target: { value } })
    }
    fireEvent.click(submitButton())
    await screen.findByText('Paramètres enregistrés')
    const body = lastPatchBody()
    for (const { key, value } of changements) {
      expect(body[key]).toBe(value)
    }
  })

  it("applique la réponse du PATCH : tarifs, interrupteurs, champs et méta-audit", async () => {
    mount()
    await settle()
    fireEvent.click(submitButton())
    await screen.findByText('Paramètres enregistrés')

    // Le tarif vient d'être remplace par la réponse serveur.
    expect(tarifInput('Licence LSF Niveau 1')).toHaveValue(6500)
    expect(tarifInput('Master Interprétation')).toHaveValue(4200)
    // Tolérance désormais active avec les valeurs serveur.
    expect(toleranceSwitch()).toBeChecked()
    expect(fieldByLabel('Tolérance fixe (minutes)')).toHaveValue(20)
    // Exports : interrupteur décoché, titres remplacés.
    expect(montantsSwitch()).not.toBeChecked()
    expect(fieldByLabel('Titre du document')).toHaveValue('FICHE ENREGISTRÉE')
    expect(fieldByLabel('Préfixe référence')).toHaveValue('SAV')
    // Méta-audit actualisé.
    const meta = screen.getByText(/Dernière mise à jour/i)
    expect(meta).toHaveTextContent('06/05/2026')
    expect(meta).toHaveTextContent(/par Marie Sauvegarde/)
  })

  it("passe en état « Enregistrement… » (bouton et champs désactivés) puis revient", async () => {
    mount()
    await settle()
    let resolvePatch
    const deferred = new Promise((res) => { resolvePatch = () => res({ data: savedSettings }) })
    apiMock.patch.mockImplementationOnce(() => deferred)

    fireEvent.click(submitButton())
    await settle(1)
    expect(submitButton()).toBeDisabled()
    expect(submitButton()).toHaveTextContent('Enregistrement…')
    expect(tarifInput('Licence LSF Niveau 1')).toBeDisabled()
    expect(toleranceSwitch()).toBeDisabled()

    resolvePatch()
    await settle()
    expect(await screen.findByText('Paramètres enregistrés')).toBeInTheDocument()
    expect(submitButton()).toBeEnabled()
    expect(submitButton()).toHaveTextContent('Enregistrer')
    expect(tarifInput('Licence LSF Niveau 1')).toBeEnabled()
  })

  it("retombe sur les valeurs par défaut quand la réponse PATCH est minimale", async () => {
    // Le serveur accuse réception sans renvoyer les réglages : toutes les
    // valeurs de repli du mapping post-PATCH sont exercées.
    mount()
    await settle()
    apiMock.patch.mockImplementationOnce(async () => ({
      data: { tarifs_formations: [] }, // ni tolérance, ni exports, ni méta-audit
    }))
    fireEvent.click(submitButton())
    await screen.findByText('Paramètres enregistrés')

    expect(screen.getByText(/aucune formation dans le référentiel/i)).toBeInTheDocument()
    expect(toleranceSwitch()).not.toBeChecked()
    fireEvent.click(toleranceSwitch())
    expect(fieldByLabel('Tolérance fixe (minutes)')).toHaveValue(30)
    expect(fieldByLabel('Tolérance relative (%)')).toHaveValue(5)
    expect(montantsSwitch()).toBeChecked()
    expect(fieldByLabel('Titre du document')).toHaveValue('FICHE DE PAIE DÉTAILLÉE')
    expect(fieldByLabel('Préfixe référence')).toHaveValue('EFI')
    expect(fieldByLabel('Organisme')).toHaveValue('')
    expect(fieldByLabel('Texte institutionnel')).toHaveValue('')
    expect(screen.queryByText(/Dernière mise à jour/i)).toBeNull()

    // Second cas dégradé : aucune donnée du tout (data null).
    apiMock.patch.mockImplementationOnce(async () => ({ data: null }))
    fireEvent.click(submitButton())
    await screen.findAllByText('Paramètres enregistrés')
    expect(fieldByLabel('Titre du document')).toHaveValue('FICHE DE PAIE DÉTAILLÉE')
    expect(fieldByLabel('Préfixe référence')).toHaveValue('EFI')
    expect(screen.getByText(/aucune formation dans le référentiel/i)).toBeInTheDocument()
  })

  it("affiche le détail d'une erreur de sauvegarde puis le message générique", async () => {
    mount()
    await settle()

    apiMock.patch.mockRejectedValueOnce({ response: { data: { detail: 'Montant hors plage' } } })
    fireEvent.click(submitButton())
    expect(await screen.findByText('Montant hors plage')).toBeInTheDocument()
    await settle()
    expect(submitButton()).toBeEnabled()

    apiMock.patch.mockRejectedValueOnce(new Error('réseau'))
    fireEvent.click(submitButton())
    expect(await screen.findByText('Erreur lors de la sauvegarde')).toBeInTheDocument()
  })
})

/* ------------------------------------------------------------------ */
/* LOT 28 — valeurs par défaut, méta-audit dégradé, période partagée   */
/* ------------------------------------------------------------------ */

describe('pages/FinanceParametrage.jsx — replis défensifs et navigation (LOT 28)', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
    window.sessionStorage.clear()
  })

  const mountFresh = () => {
    const me = makeUser('FINANCE', { username: 'finance' })
    apiController.setMe(me)
    renderWithProviders(<FinanceParametrage />, {
      authUser: me, routePattern: '/finance-parametrage', initialEntries: ['/finance-parametrage'],
    })
  }

  it("applique les valeurs par défaut avec une réponse vide (data null)", async () => {
    apiController.setRoute(SETTINGS_PATH, () => null)
    mountFresh()
    await settle()
    expect(screen.getByText(/aucune formation dans le référentiel/i)).toBeInTheDocument()
    // Tolérance désactivée (30 min / 5 % une fois révélée), exports par défaut.
    expect(toleranceSwitch()).not.toBeChecked()
    fireEvent.click(toleranceSwitch())
    expect(fieldByLabel('Tolérance fixe (minutes)')).toHaveValue(30)
    expect(fieldByLabel('Tolérance relative (%)')).toHaveValue(5)
    expect(montantsSwitch()).toBeChecked()
    expect(fieldByLabel('Titre du document')).toHaveValue('FICHE DE PAIE DÉTAILLÉE')
    expect(fieldByLabel('Préfixe référence')).toHaveValue('EFI')
  })

  it("masque le méta-audit absent et encaisse une date invalide avec auteur seul", async () => {
    // Cas 1 : aucun méta-audit.
    apiController.setRoute(SETTINGS_PATH, () => ({ ...settings, updated_at: null, updated_by: null }))
    mountFresh()
    await settle()
    expect(screen.queryByText(/Dernière mise à jour/i)).toBeNull()
  })

  it("affiche un tiret sans date mais conserve l'auteur, et réciproquement", async () => {
    // Cas 1 : bloc affiché grâce à l'auteur, date absente -> tiret.
    apiController.setRoute(SETTINGS_PATH, () => ({
      ...settings, updated_at: null, updated_by: 'Auteur Seul',
    }))
    mountFresh()
    await settle()
    let meta = screen.getByText(/Dernière mise à jour/i)
    expect(meta).toHaveTextContent('-')
    expect(meta).toHaveTextContent(/par Auteur Seul/)
  })

  it("affiche la date sans la mention d'auteur quand updated_by est absent", async () => {
    // Cas 2 : date valide, pas d'auteur -> pas de « par … ».
    apiController.setRoute(SETTINGS_PATH, () => ({
      ...settings, updated_at: '2026-03-04T10:20:00Z', updated_by: null,
    }))
    const me = makeUser('FINANCE', { username: 'finance4' })
    apiController.setMe(me)
    renderWithProviders(<FinanceParametrage />, {
      authUser: me, routePattern: '/finance-parametrage', initialEntries: ['/finance-parametrage'],
    })
    await settle()
    const meta2 = screen.getByText(/Dernière mise à jour/i)
    expect(meta2).toHaveTextContent('04/03/2026')
    expect(meta2).not.toHaveTextContent(/par /)
  })

  it("rend un tiret pour une date illisible reçue du serveur", async () => {
    apiController.setRoute(SETTINGS_PATH, () => ({
      ...settings, updated_at: 'pas-une-date', updated_by: 'Auteur Seul',
    }))
    const me = makeUser('FINANCE', { username: 'finance5' })
    apiController.setMe(me)
    renderWithProviders(<FinanceParametrage />, {
      authUser: me, routePattern: '/finance-parametrage', initialEntries: ['/finance-parametrage'],
    })
    await settle()
    const meta = screen.getByText(/Dernière mise à jour/i)
    expect(meta).toHaveTextContent('-')
    expect(meta).toHaveTextContent(/par Auteur Seul/)
  })

  it("partage la période courante via sessionStorage et les liens de navigation", async () => {
    apiController.setRoute(SETTINGS_PATH, () => settings)
    mountFresh()
    await settle()
    const stored = window.sessionStorage.getItem('finance_list_query')
    expect(stored).toContain('preset=mois')
    expect(stored).toContain(`mois=${moisCourant()}`)
    const dashboard = screen.getByRole('link', { name: /tableau de bord/i })
    expect(dashboard).toHaveAttribute(
      'href',
      expect.stringContaining(`/finance-dashboard?preset=mois&mois=${moisCourant()}`),
    )
  })
})
