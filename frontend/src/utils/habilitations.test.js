import { describe, it, expect, vi } from 'vitest'
import {
  libelleStatut, libelleCanal, libelleDomaine, compterParModule,
  resumerDifferential, differentialAvertissementBloquant,
  peutValiderModification, analyserCsv, lignesCsvVersImport, normaliserCle,
  telechargerCsv,
} from './habilitations'

describe('utils/habilitations — libellés', () => {
  it('traduit les statuts, canaux et domaines, avec repli sur la valeur brute', () => {
    expect(libelleStatut('SUSPENDU')).toBe('Suspendu')
    expect(libelleStatut('INCONNU')).toBe('INCONNU')
    expect(libelleCanal('MOBILE')).toBe('Mobile')
    expect(libelleDomaine('PEDAGOGIE')).toBe('Pédagogie')
    expect(libelleDomaine('')).toBe('—')
  })

  it('compte les permissions par module à partir du préfixe du code', () => {
    expect(compterParModule([
      'evaluations.note.saisir', 'evaluations.qcm.coriger',
      'scolarite.inscription.creer',
    ])).toEqual({ evaluations: 2, scolarite: 1 })
  })
})

describe('utils/habilitations — différentiel', () => {
  const differential = {
    gagnes: ['a.un.voir', 'a.deux.voir', 'b.x.faire'],
    perdus: ['a.trois.voir'],
    conserves: ['z.garder.voir'],
    roles_ajoutes: ['ROLE_A'],
    roles_retires: ['ROLE_B'],
    avertissements: [{ code: 'MODULE_REQUIS_ABSENT', message: 'Module absent.' }],
    total_actuel: 2, total_cible: 4,
  }

  it('résume les totaux et regroupe par module', () => {
    const r = resumerDifferential(differential)
    expect(r.totalGagnes).toBe(3)
    expect(r.totalPerdus).toBe(1)
    expect(r.gagnesParModule).toEqual({ a: 2, b: 1 })
    expect(r.perdusParModule).toEqual({ a: 1 })
    expect(r.rolesAjoutes).toEqual(['ROLE_A'])
    expect(r.rolesRetires).toEqual(['ROLE_B'])
    expect(r.vide).toBe(false)
  })

  it('considère un différentiel sans gains ni pertes comme vide', () => {
    expect(resumerDifferential({ gagnes: [], perdus: [] }).vide).toBe(true)
  })

  it('ne bloque que sur l\'avertissement SEUIL_ADMINISTRATEURS', () => {
    expect(differentialAvertissementBloquant(
      resumerDifferential(differential))).toBe(false)
    expect(differentialAvertissementBloquant(resumerDifferential({
      gagnes: [], perdus: ['x.y.z'],
      avertissements: [{ code: 'SEUIL_ADMINISTRATEURS', message: 'sous 2' }],
    }))).toBe(true)
  })

  it('refuse la validation sans résumé, sans acquittement, ou en alerte bloquante', () => {
    const resume = resumerDifferential(differential)
    expect(peutValiderModification(null, true)).toBe(false)
    expect(peutValiderModification(resume, false)).toBe(false)
    expect(peutValiderModification(resume, true)).toBe(true)
  })

  it('accepte sans case quand rien ne change, mais jamais sous le seuil admin', () => {
    expect(peutValiderModification(resumerDifferential({ gagnes: [], perdus: [] }), false)).toBe(true)
    const seuil = resumerDifferential({
      gagnes: [], perdus: ['x.y.z'],
      avertissements: [{ code: 'SEUIL_ADMINISTRATEURS', message: 'sous 2' }],
    })
    expect(peutValiderModification(seuil, true)).toBe(false)
  })
})

describe('utils/habilitations — CSV', () => {
  it('normalise les clés (accents, casse, ponctuation)', () => {
    expect(normaliserCle('Prénom')).toBe('prenom')
    expect(normaliserCle('Mot de passe')).toBe('mot_de_passe')
  })

  it('lit du CSV point-virgule avec en-têtes accentués', () => {
    const lignes = analyserCsv('Prénom;Nom;Email\nAwa;Koné;awa@injs.ci')
    expect(lignes).toEqual([{ prenom: 'Awa', nom: 'Koné', email: 'awa@injs.ci' }])
  })

  it('accepte aussi la virgule, les guillemets et ignore les lignes vides', () => {
    const lignes = analyserCsv('"nom","prenom"\n"Diop","Moussa"\n\n')
    expect(lignes).toEqual([{ nom: 'Diop', prenom: 'Moussa' }])
  })

  it('retourne un tableau vide si aucun contenu', () => {
    expect(analyserCsv('')).toEqual([])
  })

  it('convertit les lignes en charge utile import avec les alias d\'en-têtes', () => {
    const [l] = lignesCsvVersImport(analyserCsv(
      'username,prenom,motdepasse,role\ncurp_x,Fatou,secret123,SECRETARIAT',
    ))
    expect(l).toMatchObject({
      username: 'curp_x', prenoms: 'Fatou', mot_de_passe: 'secret123',
      roles: 'SECRETARIAT', canal: 'WEB',
    })
  })
})

describe('telechargerCsv', () => {
  it('construit un CSV point-virgule avec échappement des cellules', () => {
    const clic = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    URL.createObjectURL = vi.fn(() => 'blob:test')
    URL.revokeObjectURL = vi.fn(() => {})
    const creer = URL.createObjectURL
    telechargerCsv('essai.csv', ['a', 'b'], [['1', 'valeur; spéciale'], ['2', 'ligne']])
    expect(clic).toHaveBeenCalledTimes(1)
    expect(creer).toHaveBeenCalledTimes(1)
    const blob = creer.mock.calls[0][0]
    expect(blob.type).toContain('text/csv')
  })
})
