/**
 * LOT 27 — Finance : rapport des encadrants (`pages/FinanceEncadrants.jsx`).
 * Volumes horaires planifiés/réalisés par encadrant et par groupe, avec
 * période partagée (financePeriod), exports PDF/Excel et filets d'erreur.
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
import FinanceEncadrants from '@/pages/FinanceEncadrants'

const DATA_PATH = '/formations/finance/encadrants/'
const PDF_PATH = '/exports/finance/encadrants/pdf/'
const XLSX_PATH = '/exports/finance/encadrants/excel/'

const moisCourant = () => {
  const n = new Date()
  return `${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, '0')}`
}
const anneeCourante = () => String(new Date().getFullYear())

/* ------------------------------------------------------------------ */
/* Jeux de données                                                      */
/* ------------------------------------------------------------------ */

// Deux encadrants : le premier avec deux lignes (dont une sans libellés),
// le second sans aucune ligne. Les totaux couvrent les arrondis de
// fmtDuration (heures pleines et minutes).
const rapport = {
  encadrants: [
    {
      encadrant_id: 201, encadrant_label: 'Mariam Traoré', encadrant_username: 'mtraore',
      sous_total: { planned_minutes: 600, realized_minutes: 450 },
      lignes: [
        { module_id: 77, groupe: 'G1', grade: 'L1', module_intitule: 'LSF Niveau 1', formation_intitule: 'Formation LSF 2026', sessions_count: 10, planned_minutes: 300, realized_minutes: 240 },
        { module_id: 78, groupe: 'G2', grade: '', module_intitule: '', formation_intitule: '', sessions_count: 0, planned_minutes: 180, realized_minutes: 90 },
      ],
    },
    {
      encadrant_id: 202, encadrant_label: '', encadrant_username: 'kdiop',
      sous_total: { planned_minutes: 120, realized_minutes: null },
      lignes: [],
    },
  ],
  totaux: { encadrants_count: 2, planned_minutes: 720, realized_minutes: 450 },
}

// Variante « année » : 5 encadrants pour distinguer le rechargement.
const rapportAnnee = {
  encadrants: [
    { encadrant_id: 201, encadrant_label: 'Année Complète', encadrant_username: 'annee',
      sous_total: { planned_minutes: 60, realized_minutes: 30 }, lignes: [] },
  ],
  totaux: { encadrants_count: 5, planned_minutes: 6000, realized_minutes: 3000 },
}

/* ------------------------------------------------------------------ */
/* Helpers                                                              */
/* ------------------------------------------------------------------ */

const settle = async (n = 5) => { await act(async () => { await flushPromises(n) }) }

const mount = () => {
  const me = makeUser('FINANCE', { username: 'finance' })
  apiController.setMe(me)
  return renderWithProviders(<FinanceEncadrants />, {
    authUser: me,
    routePattern: '/finance-encadrants',
    initialEntries: ['/finance-encadrants'],
  })
}

const dataCalls = () =>
  apiMock.get.mock.calls
    .filter(([p]) => p.startsWith(DATA_PATH))
    .map(([p]) => new URL(p, 'http://testserver').searchParams)
const lastParams = () => dataCalls().at(-1)

const filterPanel = () => document.querySelector('.finance-filter-panel')
const applyButton = () => within(filterPanel()).getByRole('button', { name: /appliquer/i })
// Les <label> du filtre ne sont pas reliés par htmlFor : champ du bloc voisin.
const periodField = (labelText) => {
  const label = within(filterPanel()).getByText((_c, el) => el.tagName === 'LABEL' && el.textContent === labelText)
  return label.parentElement.querySelector('input')
}

const stubBlobDownload = () => {
  URL.createObjectURL = vi.fn(() => 'blob:test')
  URL.revokeObjectURL = vi.fn()
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
}

const sectionFor = (headingRegex) =>
  screen.getByRole('heading', { name: headingRegex }).closest('section')

/* ------------------------------------------------------------------ */
/* LOT 27 — chargement, navigation, KPI                                */
/* ------------------------------------------------------------------ */

describe('pages/FinanceEncadrants.jsx — chargement et synthèse (LOT 27)', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
    window.sessionStorage.clear()
    apiController.setRoute(DATA_PATH, (path) =>
      path.includes('preset=annee') ? rapportAnnee : rapport,
    )
  })

  it('charge le rapport du mois courant et affiche titre, sous-titre et navigation', async () => {
    mount()
    await settle()

    expect(screen.getByRole('heading', { name: 'Encadrants', level: 1 })).toBeInTheDocument()
    expect(screen.getByText(/volumes horaires planifiés et réalisés/i)).toBeInTheDocument()
    for (const label of ['Tableau de bord', 'Enseignants', 'Ajustements', 'Paramétrage']) {
      expect(screen.getByRole('link', { name: new RegExp(label, 'i') })).toBeInTheDocument()
    }
    // L'onglet courant est accentué.
    const lienActif = screen.getByRole('link', { name: /encadrants/i })
    expect(lienActif).toHaveClass('btn-finance-accent')

    const params = lastParams()
    expect(params.get('preset')).toBe('mois')
    expect(params.get('mois')).toBe(moisCourant())
  })

  it('affiche le spinner pendant le chargement puis les trois KPI formatés', async () => {
    const { container } = mount()
    expect(container.querySelector('.loading .spinner')).toBeTruthy()
    await settle()

    // 2 encadrants ; 720 min = 12h planifié ; 450 min = 7h 30min réalisé.
    expect(document.querySelector('.finance-hero-kpi--rate .finance-hero-kpi-value')).toHaveTextContent('2')
    expect(document.querySelector('.finance-hero-kpi--plan .finance-hero-kpi-value')).toHaveTextContent('12h')
    expect(document.querySelector('.finance-hero-kpi--time .finance-hero-kpi-value')).toHaveTextContent('7h 30min')
  })

  it('détaille chaque encadrant : section, badge de sous-total, lignes et totaux', async () => {
    mount()
    await settle()

    const section = sectionFor(/Mariam Traoré/)
    // Badge d'en-tête : 600 min = 10h planifié, 450 = 7h 30min réalisé.
    expect(within(section).getByText(/10h planifié/)).toHaveTextContent('10h planifié · 7h 30min réalisé')

    for (const col of ['Groupe', 'Grade', 'Module', 'Formation', 'Séances', 'Planifié', 'Réalisé']) {
      expect(within(section).getByRole('columnheader', { name: col })).toBeInTheDocument()
    }

    // Première ligne, valeurs complètes.
    expect(within(section).getByText('G1')).toBeInTheDocument()
    expect(within(section).getByText('L1')).toBeInTheDocument()
    expect(within(section).getByText('LSF Niveau 1')).toBeInTheDocument()
    expect(within(section).getByText('Formation LSF 2026')).toBeInTheDocument()
    expect(within(section).getByText('10')).toBeInTheDocument()
    expect(within(section).getByText('5h')).toBeInTheDocument() // 300 min planifié
    expect(within(section).getByText('4h')).toBeInTheDocument() // 240 min réalisé
    expect(within(section).getByText('3h')).toBeInTheDocument() // 180 min planifié
    expect(within(section).getByText('1h 30min')).toBeInTheDocument() // 90 min réalisé

    // Seconde ligne sans libellés : trois tirets de repli.
    expect(within(section).getAllByText('—').length).toBeGreaterThanOrEqual(3)
    expect(within(section).getByText('G2')).toBeInTheDocument()

    // Pied de tableau : sous-totaux en gras.
    const tfoot = section.querySelector('tfoot')
    expect(tfoot).toHaveTextContent('Sous-total')
    expect(tfoot).toHaveTextContent('10h')
    expect(tfoot).toHaveTextContent('7h 30min')
  })

  it("replie sur le nom d'utilisateur et rend un encadrant sans lignes (0h)", async () => {
    mount()
    await settle()
    const section = sectionFor(/kdiop/)
    // 120 min = 2h planifié ; réalisé null → 0h.
    expect(within(section).getByText(/2h planifié · 0h réalisé/)).toBeInTheDocument()
    expect(section.querySelectorAll('tbody tr')).toHaveLength(0)
    // Le pied de tableau reste présent.
    expect(section.querySelector('tfoot')).toHaveTextContent('Sous-total')
  })

  it("affiche l'état vide et des KPI à zéro sans aucune activité", async () => {
    apiController.reset()
    const me = makeUser('FINANCE', { username: 'finance' })
    apiController.setMe(me)
    apiController.setRoute(DATA_PATH, () => ({ encadrants: [], totaux: {} }))
    renderWithProviders(<FinanceEncadrants />, {
      authUser: me, routePattern: '/finance-encadrants', initialEntries: ['/finance-encadrants'],
    })
    await settle()
    expect(screen.getByText(/aucun encadrant avec activité/i)).toBeInTheDocument()
    expect(document.querySelector('.finance-hero-kpi--rate .finance-hero-kpi-value')).toHaveTextContent('0')
    expect(document.querySelector('.finance-hero-kpi--plan .finance-hero-kpi-value')).toHaveTextContent('0h')
  })

  it("ne plante pas avec une réponse vide (data null), état vide", async () => {
    apiController.reset()
    const me = makeUser('FINANCE', { username: 'finance' })
    apiController.setMe(me)
    apiController.setRoute(DATA_PATH, () => null)
    renderWithProviders(<FinanceEncadrants />, {
      authUser: me, routePattern: '/finance-encadrants', initialEntries: ['/finance-encadrants'],
    })
    await settle()
    expect(screen.getByText(/aucun encadrant avec activité/i)).toBeInTheDocument()
  })

  it("affiche le détail d'une erreur serveur au chargement", async () => {
    apiController.reset()
    const me = makeUser('FINANCE', { username: 'finance' })
    apiController.setMe(me)
    apiController.setRoute(DATA_PATH, () => {
      // eslint-disable-next-line no-throw-literal
      throw { response: { data: { detail: 'Périmètre finance indisponible' } } }
    })
    renderWithProviders(<FinanceEncadrants />, {
      authUser: me, routePattern: '/finance-encadrants', initialEntries: ['/finance-encadrants'],
    })
    expect(await screen.findByText('Périmètre finance indisponible')).toBeInTheDocument()
  })

  it("affiche un message générique quand l'erreur de chargement n'a pas de détail", async () => {
    apiController.reset()
    const me = makeUser('FINANCE', { username: 'finance' })
    apiController.setMe(me)
    apiController.setRoute(DATA_PATH, () => {
      // eslint-disable-next-line no-throw-literal
      throw { response: { data: {} } }
    })
    renderWithProviders(<FinanceEncadrants />, {
      authUser: me, routePattern: '/finance-encadrants', initialEntries: ['/finance-encadrants'],
    })
    expect(await screen.findByText('Impossible de charger le rapport encadrants.')).toBeInTheDocument()
  })
})

/* ------------------------------------------------------------------ */
/* LOT 27 — périodes                                                   */
/* ------------------------------------------------------------------ */

describe('pages/FinanceEncadrants.jsx — filtre de période (LOT 27)', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
    window.sessionStorage.clear()
    apiController.setRoute(DATA_PATH, (path) =>
      path.includes('preset=annee') ? rapportAnnee : rapport,
    )
  })

  it("applique « Cette année » après le clic sur Appliquer (nouvelle requête)", async () => {
    mount()
    await settle()
    expect(lastParams().get('preset')).toBe('mois')

    fireEvent.click(within(filterPanel()).getByRole('button', { name: 'Cette année' }))
    // La requête ne change pas avant Appliquer.
    await settle()
    expect(lastParams().get('preset')).toBe('mois')

    fireEvent.click(applyButton())
    await waitFor(() => expect(lastParams().get('preset')).toBe('annee'))
    expect(lastParams().get('annee')).toBe(anneeCourante())

    // Les données de la variante année s'affichent (5 encadrants).
    expect(document.querySelector('.finance-hero-kpi--rate .finance-hero-kpi-value')).toHaveTextContent('5')
    expect(sectionFor(/Année Complète/)).toBeInTheDocument()
    // La période est persistée pour la navigation entre pages finance.
    expect(window.sessionStorage.getItem('finance_period')).toContain('"annee"')
  })

  it('applique un trimestre choisi (T1) avec sa clé YYYY-Qn', async () => {
    mount()
    await settle()
    fireEvent.click(within(filterPanel()).getByRole('button', { name: 'Trimestre' }))
    fireEvent.click(within(filterPanel()).getByRole('button', { name: 'T1' }))
    fireEvent.click(applyButton())
    await waitFor(() => expect(lastParams().get('preset')).toBe('trimestre'))
    expect(lastParams().get('trimestre')).toBe(`${anneeCourante()}-Q1`)
  })

  it('applique une période personnalisée avec les deux dates', async () => {
    mount()
    await settle()
    fireEvent.click(within(filterPanel()).getByRole('button', { name: 'Personnalisé' }))
    fireEvent.change(periodField('Du'), { target: { value: '2026-01-10' } })
    fireEvent.change(periodField('Au'), { target: { value: '2026-02-10' } })
    fireEvent.click(applyButton())
    await waitFor(() => expect(lastParams().get('preset')).toBe('custom'))
    expect(lastParams().get('date_debut')).toBe('2026-01-10')
    expect(lastParams().get('date_fin')).toBe('2026-02-10')
  })

  it("désactive Appliquer si une date personnalisée manque", async () => {
    mount()
    await settle()
    fireEvent.click(within(filterPanel()).getByRole('button', { name: 'Personnalisé' }))
    expect(applyButton()).toBeEnabled() // dates du mois préremplies
    fireEvent.change(periodField('Du'), { target: { value: '' } })
    expect(applyButton()).toBeDisabled()
    fireEvent.change(periodField('Du'), { target: { value: '2026-01-01' } })
    expect(applyButton()).toBeEnabled()
  })
})

/* ------------------------------------------------------------------ */
/* LOT 27 — exports                                                    */
/* ------------------------------------------------------------------ */

describe('pages/FinanceEncadrants.jsx — exports (LOT 27)', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
    window.sessionStorage.clear()
    apiController.setRoute(DATA_PATH, () => rapport)
    stubBlobDownload()
  })

  it('exporte la liste en Excel sur la période courante et notifie', async () => {
    mount()
    await settle()
    fireEvent.click(screen.getByRole('button', { name: /encadrants excel/i }))
    await waitFor(() => {
      const appel = apiMock.getBlob.mock.calls.at(-1)[0]
      expect(appel.startsWith(XLSX_PATH)).toBe(true)
      const q = new URL(appel, 'http://testserver').searchParams
      expect(q.get('preset')).toBe('mois')
      expect(q.get('mois')).toBe(moisCourant())
    })
    expect(await screen.findByText('Liste encadrants exportée (XLSX)')).toBeInTheDocument()
    expect(HTMLAnchorElement.prototype.click).toHaveBeenCalledTimes(1)
    expect(URL.revokeObjectURL).toHaveBeenCalled()
  })

  it('exporte la liste en PDF', async () => {
    mount()
    await settle()
    fireEvent.click(screen.getByRole('button', { name: /encadrants pdf/i }))
    await waitFor(() => {
      const appel = apiMock.getBlob.mock.calls.at(-1)[0]
      expect(appel.startsWith(PDF_PATH)).toBe(true)
    })
    expect(await screen.findByText('Liste encadrants exportée (PDF)')).toBeInTheDocument()
  })

  it("reporte la période appliquée sur l'export", async () => {
    mount()
    await settle()
    fireEvent.click(within(filterPanel()).getByRole('button', { name: 'Cette année' }))
    fireEvent.click(applyButton())
    await waitFor(() => expect(lastParams().get('preset')).toBe('annee'))

    fireEvent.click(screen.getByRole('button', { name: /encadrants pdf/i }))
    await waitFor(() => {
      const appel = apiMock.getBlob.mock.calls.at(-1)[0]
      const q = new URL(appel, 'http://testserver').searchParams
      expect(q.get('preset')).toBe('annee')
      expect(q.get('annee')).toBe(anneeCourante())
    })
  })

  it("notifie le détail d'une erreur d'export puis le message générique", async () => {
    mount()
    await settle()
    apiMock.getBlob.mockRejectedValueOnce({ response: { data: { detail: 'Génération PDF KO' } } })
    fireEvent.click(screen.getByRole('button', { name: /encadrants pdf/i }))
    expect(await screen.findByText('Génération PDF KO')).toBeInTheDocument()

    apiMock.getBlob.mockRejectedValueOnce(new Error('réseau'))
    fireEvent.click(screen.getByRole('button', { name: /encadrants pdf/i }))
    expect(await screen.findByText('Erreur export encadrants')).toBeInTheDocument()
  })

  it("utilise le nom de fichier par défaut quand le serveur n'en fournit pas", async () => {
    mount()
    await settle()
    apiMock.getBlob.mockResolvedValueOnce({
      blob: new Blob(['x'], { type: 'application/pdf' }), fileName: '',
    })
    // On intercepte l'ancre créée pour lire son attribut download.
    let ancres = []
    const appendSpy = vi.spyOn(document.body, 'appendChild').mockImplementation((el) => {
      ancres.push(el)
      return el
    })
    fireEvent.click(screen.getByRole('button', { name: /encadrants pdf/i }))
    await waitFor(() => expect(ancres.length).toBeGreaterThan(0))
    expect(ancres[0].getAttribute('download')).toBe('liste_encadrants.pdf')
    appendSpy.mockRestore()
  })
})

describe('pages/FinanceEncadrants.jsx — données et périodes dégradées (LOT 27)', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
    window.sessionStorage.clear()
    stubBlobDownload()
  })

  const mountWith = () => {
    const me = makeUser('FINANCE', { username: 'finance' })
    apiController.setMe(me)
    return renderWithProviders(<FinanceEncadrants />, {
      authUser: me, routePattern: '/finance-encadrants', initialEntries: ['/finance-encadrants'],
    })
  }

  it("supporte une période sans preset : requêtes et export sans query string", async () => {
    // Une période persistée dégradée (sans preset) produit une query vide :
    // les appels doivent tomber sur les chemins de base, sans « ? ».
    window.sessionStorage.setItem('finance_period', JSON.stringify({ preset: '' }))
    apiController.setRoute(DATA_PATH, () => rapport)
    mountWith()
    await settle()
    expect(apiMock.get).toHaveBeenCalledWith(DATA_PATH)

    fireEvent.click(screen.getByRole('button', { name: /encadrants excel/i }))
    await waitFor(() =>
      expect(apiMock.getBlob).toHaveBeenCalledWith('/exports/finance/encadrants/excel/'),
    )
  })

  it("encaisse des lignes et compteurs absents (replis défensifs)", async () => {
    apiController.setRoute(DATA_PATH, () => ({
      encadrants: [
        {
          encadrant_id: 301, encadrant_label: 'Encadrant Minimal',
          // ni sous_total, ni lignes
        },
        {
          encadrant_id: 302, encadrant_username: 'nu',
          sous_total: {},
          lignes: [{ module_id: 9, groupe: 'G9' /* pas de sessions_count */ }],
        },
      ],
      // pas de totaux
    }))
    mountWith()
    await settle()
    expect(document.querySelector('.finance-hero-kpi--rate .finance-hero-kpi-value')).toHaveTextContent('0')
    const section2 = sectionFor(/^nu$/)
    // sessions_count absent → 0.
    expect(within(section2).getByText('0')).toBeInTheDocument()
    // Première section sans lignes : aucun corps de tableau.
    expect(sectionFor(/Encadrant Minimal/).querySelectorAll('tbody tr')).toHaveLength(0)
  })
})
