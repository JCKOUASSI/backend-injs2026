import { describe, it, expect, beforeEach, vi } from 'vitest'

const m = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  delete: vi.fn(),
  getBlob: vi.fn(),
}))

vi.mock('@/services/api', () => ({ default: m }))

import * as svc from '@/services/scolarite'

beforeEach(() => {
  vi.clearAllMocks()
  m.get.mockResolvedValue({ data: {}, status: 200 })
  m.post.mockResolvedValue({ data: {}, status: 201 })
  m.patch.mockResolvedValue({ data: {}, status: 200 })
  m.delete.mockResolvedValue({ data: null, status: 204 })
  m.getBlob.mockResolvedValue({ blob: new Blob(), fileName: 'f', contentType: 'text/csv' })
})

describe('services/scolarite.js — construction des appels', () => {
  it('getAnneeCourante renvoie l’année ou null', async () => {
    m.get.mockResolvedValueOnce({ data: { annee: '2025-2026' } })
    await expect(svc.getAnneeCourante()).resolves.toBe('2025-2026')
    m.get.mockResolvedValueOnce({ data: {} })
    await expect(svc.getAnneeCourante()).resolves.toBeNull()
  })

  // Pour chaque fonction, vérifie la méthode HTTP et le chemin appelé.
  const cases = [
    ['getRefScolarite', ['niveaux'], 'get', '/scolarite/ref/niveaux/'],
    ['getRefAdmission', ['types'], 'get', '/admissions/ref/types/'],
    ['getRefFormations', [], 'get', '/formations/ref/formations/'],
    ['getRefCategories', [], 'get', '/formations/ref/categories/'],
    ['getRefGrades', [], 'get', '/formations/ref/grades/'],
    ['getRefVagues', [], 'get', '/formations/ref/vagues/'],
    ['getFormationsOperationnelles', [], 'get', '/formations/formations/'],
    ['listCandidatures', [{ q: 'a' }], 'get', '/admissions/candidatures/'],
    ['getCandidature', [9], 'get', '/admissions/candidatures/9/'],
    ['createCandidature', [{ nom: 'x' }], 'post', '/admissions/candidatures/'],
    ['updateCandidature', [9, { nom: 'y' }], 'patch', '/admissions/candidatures/9/'],
    ['transitionCandidature', [9, { action: 'soumettre' }], 'post', '/admissions/candidatures/9/transition/'],
    ['getStatsCandidatures', [{}], 'get', '/admissions/candidatures/stats/'],
    ['listCandidats', [{}], 'get', '/admissions/candidats/'],
    ['createCandidat', [{ nom: 'z' }], 'post', '/admissions/candidats/'],
    ['getPieces', [3], 'get', '/admissions/candidatures/3/pieces/'],
    ['initPieces', [3], 'post', '/admissions/candidatures/3/pieces/'],
    ['deposerPiece', [5, new FormData()], 'post', '/admissions/pieces/5/deposer/'],
    ['verifierPiece', [5, { ok: true }], 'post', '/admissions/pieces/5/verifier/'],
    ['telechargerPiece', [5], 'getBlob', '/admissions/pieces/5/fichier/'],
    ['listAdmissions', [{}], 'get', '/admissions/admissions/'],
    ['createAdmission', [{}], 'post', '/admissions/admissions/'],
    ['updateAdmission', [2, {}], 'patch', '/admissions/admissions/2/'],
    ['decisionAdmission', [2, { decision: 'ADMIS' }], 'post', '/admissions/admissions/2/decision/'],
    ['annulerAdmission', [2, { motif: 'm' }], 'post', '/admissions/admissions/2/annuler/'],
    ['getStatsAdmissions', [{}], 'get', '/admissions/admissions/stats/'],
    ['listEtudiants', [{}], 'get', '/scolarite/etudiants/'],
    ['getEtudiant', [4], 'get', '/scolarite/etudiants/4/'],
    ['updateEtudiant', [4, {}], 'patch', '/scolarite/etudiants/4/'],
    ['listInscriptions', [{}], 'get', '/scolarite/inscriptions/'],
    ['getInscription', [4], 'get', '/scolarite/inscriptions/4/'],
    ['updateInscription', [4, {}], 'patch', '/scolarite/inscriptions/4/'],
    ['transitionInscription', [4, { action: 'valider' }], 'post', '/scolarite/inscriptions/4/transition/'],
    ['inscrireDepuisAdmission', [{}], 'post', '/scolarite/inscriptions/depuis-admission/'],
    ['getStatsInscriptions', [{}], 'get', '/scolarite/inscriptions/stats/'],
    ['getPedagogie', [4, {}], 'get', '/scolarite/inscriptions/4/pedagogie/'],
    ['genererPedagogie', [4, {}], 'post', '/scolarite/inscriptions/4/pedagogie/generer/'],
    ['ajouterEcue', [4, {}], 'post', '/scolarite/inscriptions/4/pedagogie/ajouter/'],
    ['retirerEcue', [7], 'delete', '/scolarite/pedagogie/7/'],
    ['getEffectifsGroupes', [{}], 'get', '/scolarite/groupes/effectifs/'],
    ['getAffectations', [4], 'get', '/scolarite/inscriptions/4/affectations/'],
    ['affecterGroupe', [4, {}], 'post', '/scolarite/inscriptions/4/affectations/'],
    ['retirerGroupe', [4, {}], 'post', '/scolarite/inscriptions/4/retirer-groupe/'],
    ['repartirGroupes', [{}], 'post', '/scolarite/groupes/repartition/'],
    ['reinscrire', [{}], 'post', '/scolarite/reinscriptions/'],
    ['getEvenements', [4], 'get', '/scolarite/etudiants/4/evenements/'],
    ['createEvenement', [4, {}], 'post', '/scolarite/etudiants/4/evenements/'],
    ['analyserPasserelle', [4, {}], 'post', '/scolarite/inscriptions/4/passerelle/analyser/'],
    ['synchroniserPasserelle', [4, {}], 'post', '/scolarite/inscriptions/4/passerelle/'],
    ['synchroniserLot', [{}], 'post', '/scolarite/passerelle/lot/'],
  ]

  for (const [name, args, method, expectedPath] of cases) {
    it(`${name} → ${method.toUpperCase()} ${expectedPath}`, async () => {
      await svc[name](...args)
      expect(m[method]).toHaveBeenCalled()
      const calledPath = m[method].mock.calls.at(-1)[0]
      expect(calledPath).toBe(expectedPath)
    })
  }
})

describe('services/scolarite.js — helpers', () => {
  it('statutVariant renvoie la variante connue ou secondary', () => {
    expect(svc.statutVariant('ADMIS')).toBe('success')
    expect(svc.statutVariant('REFUSE')).toBe('danger')
    expect(svc.statutVariant('INCONNU')).toBe('secondary')
  })

  it('messageErreur gère toutes les formes', () => {
    expect(svc.messageErreur(null)).toBe('Une erreur est survenue')
    expect(svc.messageErreur({})).toBe('Une erreur est survenue')
    expect(svc.messageErreur({ response: { data: 'Message brut' } })).toBe('Message brut')
    expect(svc.messageErreur({ response: { data: { error: 'Erreur globale' } } })).toBe('Erreur globale')
    const avecChamps = svc.messageErreur({ response: { data: { nom: ['Requis'], age: 'Trop jeune' } } })
    expect(avecChamps).toContain('nom : Requis')
    expect(avecChamps).toContain('age : Trop jeune')
  })
})
