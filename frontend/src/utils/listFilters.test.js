import { describe, it, expect, beforeEach } from 'vitest'
import {
  LIST_STORAGE_KEYS,
  parseListPage,
  persistListQuery,
  listHref,
  modulesListHref,
  participantsListHref,
  usersListHref,
  formateursListHref,
  referentielsListHref,
  dashboardListHref,
  readModulesFilters,
  buildModulesSearchParams,
  readParticipantsFilters,
  buildParticipantsSearchParams,
  readUsersFilters,
  buildUsersSearchParams,
  readFormateursListExtras,
  buildFormateursListSearchParams,
  readReferentielsTab,
  buildReferentielsSearchParams,
  readDashboardFilters,
  buildDashboardSearchParams,
  readSecretariatsExpanded,
  buildSecretariatsSearchParams,
} from './listFilters'

const sp = (qs = '') => new URLSearchParams(qs)

describe('utils/listFilters — pagination d’URL', () => {
  it('parseListPage lit un numéro de page valide', () => {
    expect(parseListPage(sp('page=3'))).toBe(3)
  })

  it('retombe sur le fallback quand la page est absente, invalide, nulle ou négative', () => {
    expect(parseListPage(sp(''))).toBe(1)
    expect(parseListPage(sp(''), 5)).toBe(5)
    expect(parseListPage(sp('page=abc'))).toBe(1)
    expect(parseListPage(sp('page=0'))).toBe(1)
    expect(parseListPage(sp('page=-4'))).toBe(1)
    expect(parseListPage(sp('page=2.7'))).toBe(2)
  })
})

describe('utils/listFilters — persistance sessionStorage / liens Retour', () => {
  beforeEach(() => window.sessionStorage.clear())

  it('persistListQuery stocke la query string et la préfixe par « ? »', () => {
    const params = sp('search=dupont&page=2')
    expect(persistListQuery(LIST_STORAGE_KEYS.modules, params)).toBe('?search=dupont&page=2')
    expect(window.sessionStorage.getItem(LIST_STORAGE_KEYS.modules)).toBe('search=dupont&page=2')
  })

  it('persistListQuery renvoie une chaîne vide quand il n’y a aucun paramètre', () => {
    expect(persistListQuery('x', sp(''))).toBe('')
    expect(window.sessionStorage.getItem('x')).toBe('')
  })

  it('listHref réapplique la query stockée, sinon renvoie le chemin brut', () => {
    expect(listHref('/modules', LIST_STORAGE_KEYS.modules)).toBe('/modules')
    window.sessionStorage.setItem(LIST_STORAGE_KEYS.modules, 'statut=EN_COURS&page=4')
    expect(listHref('/modules', LIST_STORAGE_KEYS.modules)).toBe('/modules?statut=EN_COURS&page=4')
  })

  it.each([
    ['modules', modulesListHref, '/modules'],
    ['participants', participantsListHref, '/participants'],
    ['users', usersListHref, '/users'],
    ['formateurs', formateursListHref, '/formateurs'],
    ['referentiels', referentielsListHref, '/referentiels'],
    ['dashboard', dashboardListHref, '/'],
  ])('helper de lien %s pointe au bon chemin', (_nom, fn, path) => {
    expect(fn()).toBe(path)
  })

  it('expose les clés de stockage des listes principales', () => {
    expect(Object.keys(LIST_STORAGE_KEYS).sort()).toEqual(
      ['dashboard', 'formateurs', 'modules', 'participants', 'referentiels', 'secretariats', 'users'].sort(),
    )
  })
})

describe('utils/listFilters — filtres Modules', () => {
  it('readModulesFilters lit les valeurs et applique les défauts', () => {
    const f = readModulesFilters(sp('statut=TERMINE&groupe=G1'), () => '2026-01-15')
    expect(f).toMatchObject({
      statut: 'TERMINE',
      groupe: 'G1',
      search: '',
      secretariat_type: '',
      vague: '',
      grade: '',
      date_mode: 'all',
      date: '2026-01-15',
    })
  })

  it('buildModulesSearchParams omet la page en première page et les filtres vides', () => {
    const p = buildModulesSearchParams({ statut: '', search: '', date_mode: 'all', date: '2026-01-15' }, 1, '')
    expect(p.toString()).toBe('')
  })

  it('buildModulesSearchParams ajoute la page et les filtres renseignés', () => {
    const p = buildModulesSearchParams(
      { statut: 'EN_COURS', search: 'alpha', date_mode: 'all', date: '2026-01-15', grade: 'G2', vague: 'V1', secretariat_type: 'CPFAE', groupe: 'G3' },
      3,
      'alpha',
    )
    expect(p.get('page')).toBe('3')
    expect(p.get('statut')).toBe('EN_COURS')
    expect(p.get('search')).toBe('alpha')
    expect(p.get('grade')).toBe('G2')
    expect(p.get('vague')).toBe('V1')
    expect(p.get('secretariat_type')).toBe('CPFAE')
    expect(p.get('groupe')).toBe('G3')
    expect(p.has('date')).toBe(false) // date ignorée tant que date_mode ≠ « date »
    expect(p.has('date_mode')).toBe(false) // « all » n’est pas émis
  })

  it('buildModulesSearchParams n’émet la date qu’en mode « date »', () => {
    const enDate = buildModulesSearchParams({ date_mode: 'date', date: '2026-09-10' }, 1, '')
    expect(enDate.get('date_mode')).toBe('date')
    expect(enDate.get('date')).toBe('2026-09-10')
  })
})

describe('utils/listFilters — filtres Participants', () => {
  it('readParticipantsFilters par défaut', () => {
    expect(readParticipantsFilters(sp(''))).toEqual({
      search: '', sexe: '', secretariat: '', grade: '', groupe: '', type_concours: '', vague: '',
    })
  })

  it('buildParticipantsSearchParams ne garde que les valeurs truthy', () => {
    const p = buildParticipantsSearchParams(
      { search: 'x', sexe: 'F', secretariat: '', grade: 'G1', groupe: '', type_concours: 'DIRECT', vague: '' },
      2,
      'x',
    )
    expect(p.get('page')).toBe('2')
    expect(p.get('sexe')).toBe('F')
    expect(p.get('grade')).toBe('G1')
    expect(p.get('type_concours')).toBe('DIRECT')
    expect(p.has('secretariat')).toBe(false)
    expect(p.has('groupe')).toBe(false)
  })
})

describe('utils/listFilters — filtres Utilisateurs', () => {
  it('readUsersFilters : onglet par défaut « personnel »', () => {
    expect(readUsersFilters(sp(''))).toEqual({ tab: 'personnel', search: '', role: '' })
    expect(readUsersFilters(sp('tab=auditeurs'))).toEqual({ tab: 'auditeurs', search: '', role: '' })
  })

  it('buildUsersSearchParams : rôle uniquement pour l’onglet personnel', () => {
    const personnel = buildUsersSearchParams('personnel', 'FINANCE', 2, 'dupont')
    expect(personnel.get('tab')).toBe(null)
    expect(personnel.get('role')).toBe('FINANCE')
    expect(personnel.get('search')).toBe('dupont')
    expect(personnel.get('page')).toBe('2')

    const autre = buildUsersSearchParams('auditeurs', 'FINANCE', 1, 'jean')
    expect(autre.get('tab')).toBe('auditeurs')
    expect(autre.get('role')).toBe(null) // pas de filtre de rôle hors personnel
    expect(autre.get('search')).toBe('jean')
  })
})

describe('utils/listFilters — filtres Formateurs (dont extension finance)', () => {
  it('readFormateursListExtras', () => {
    expect(readFormateursListExtras(sp(''))).toEqual({ search: '' })
    expect(readFormateursListExtras(sp('search=ani'))).toEqual({ search: 'ani' })
  })

  it('buildFormateursListSearchParams construit la query par défaut', () => {
    const p = buildFormateursListSearchParams(4, 'kofi')
    expect(p.get('page')).toBe('4')
    expect(p.get('search')).toBe('kofi')
  })

  it('délègue au constructeur finance quand withFinance est actif', () => {
    const received = []
    const builder = (period, filters, extra) => {
      received.push({ period, filters, extra })
      return sp('preset=mois&mois=2026-09&search=kofi&page=4')
    }
    const period = { preset: 'mois', mois: '2026-09' }
    const p = buildFormateursListSearchParams(4, 'kofi', period, { x: 1 }, true, builder)
    expect(p.get('preset')).toBe('mois')
    expect(received[0].extra).toEqual({ page: 4, search: 'kofi' })
    expect(received[0].period).toBe(period)
  })
})

describe('utils/listFilters — filtres Référentiels', () => {
  it('readReferentielsTab valide l’onglet (liste blanche)', () => {
    expect(readReferentielsTab(sp(''))).toBe('formations')
    expect(readReferentielsTab(sp('tab=salles'))).toBe('salles')
    expect(readReferentielsTab(sp('tab=inconnu'))).toBe('formations')
  })

  it('buildReferentielsSearchParams n’émet que les onglets non définaut', () => {
    expect(buildReferentielsSearchParams('formations').toString()).toBe('')
    expect(buildReferentielsSearchParams('grades').get('tab')).toBe('grades')
  })
})

describe('utils/listFilters — filtres Dashboard / statistiques', () => {
  it('readDashboardFilters applique les défauts', () => {
    const f = readDashboardFilters(sp(''))
    expect(f.secretariat).toBe('')
    expect(f.presence_period).toBe('jour')
    expect(f.reference_date).toMatch(/^\d{4}-\d{2}-\d{2}$/)
  })

  // Régression §10.17 (corrigé au LOT 43) : une présence_period inconnue est
  // normalisée vers « jour » au lieu de faire planter le rendu du Dashboard.
  it('readDashboardFilters normalise une presence_period inconnue vers le jour (§10.17)', () => {
    expect(readDashboardFilters(sp('?presence_period=bizarre')).presence_period).toBe('jour')
    expect(readDashboardFilters(sp('?presence_period=JOUR')).presence_period).toBe('jour')
    for (const period of ['semaine', 'mois', 'annee']) {
      expect(readDashboardFilters(sp(`?presence_period=${period}`)).presence_period).toBe(period)
    }
  })

  // Régression §10.17 : une référence invalide (ou un jour inexistant) est
  // remplacée par la date du jour plutôt que de produire « Invalid Date ».
  it('readDashboardFilters remplace une reference_date invalide par aujourd’hui (§10.17)', () => {
    const today = new Date().toISOString().slice(0, 10)
    expect(readDashboardFilters(sp('?reference_date=date-invalide')).reference_date).toBe(today)
    expect(readDashboardFilters(sp('?reference_date=2026-13-40')).reference_date).toBe(today)
    expect(readDashboardFilters(sp('?reference_date=2026-01-15')).reference_date).toBe('2026-01-15')
  })

  it('buildDashboardSearchParams omet les valeurs par défaut (jour / aujourd’hui)', () => {
    const today = new Date().toISOString().slice(0, 10)
    const p = buildDashboardSearchParams({ secretariat: '', presence_period: 'jour', reference_date: today })
    expect(p.toString()).toBe('')
  })

  it('buildDashboardSearchParams émet secrétariat, période et date de référence', () => {
    const p = buildDashboardSearchParams(
      { secretariat: '7', presence_period: 'semaine', reference_date: '2026-05-01' },
    )
    expect(p.get('secretariat')).toBe('7')
    expect(p.get('presence_period')).toBe('semaine')
    expect(p.get('reference_date')).toBe('2026-05-01')
  })

  it('buildDashboardSearchParams ajoute la période finance quand fournie', () => {
    const p = buildDashboardSearchParams(
      { secretariat: '', presence_period: 'jour', reference_date: '2026-01-01' },
      { preset: 'annee', annee: '2026' },
    )
    expect(p.get('preset')).toBe('annee')
    expect(p.get('annee')).toBe('2026')
  })
})

describe('utils/listFilters — filtres Secrétariats (panneau déplié)', () => {
  it('readSecretariatsExpanded', () => {
    expect(readSecretariatsExpanded(sp(''))).toBe('')
    expect(readSecretariatsExpanded(sp('expanded=12'))).toBe('12')
  })

  it('buildSecretariatsSearchParams', () => {
    expect(buildSecretariatsSearchParams('').toString()).toBe('')
    expect(buildSecretariatsSearchParams(null).toString()).toBe('')
    expect(buildSecretariatsSearchParams(12).get('expanded')).toBe('12')
  })
})
