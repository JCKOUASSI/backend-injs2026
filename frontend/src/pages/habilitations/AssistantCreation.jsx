/** AssistantCreation — création de compte en 5 étapes avec récapitulatif clair. */
import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useDebounce } from '@/hooks/useDebounce'
import { useSecretariats } from '@/hooks/useSecretariats'
import { useAuth } from '@/context/AuthContext'
import { useToast } from '@/context/ToastContext'
import {
  creerCompte, listerRolesCurp, rechercherPersonnes, messageErreur,
} from '@/services/habilitations'
import { BadgeSensible } from './partages'
import {
  EtapeCompte, EtapePerimetres, EtapePersonne, EtapeRoles,
} from './AssistantEtapes'
import './habilitations.css'

const ETAPES = ['Identité', 'Connexion', 'Rôles', 'Périmètres', 'Récapitulatif']
const personneVide = { resultatSelectionne: null, matricule: '', nom: '', prenoms: '', email: '', telephone: '', service: '' }
const compteVide = { username: '', email: '', mot_de_passe: '', role_legacy: '', canal: 'WEB' }

export default function AssistantCreation() {
  const navigate = useNavigate()
  const { showToast } = useToast()
  const { user } = useAuth()
  const { data: secretariats = [] } = useSecretariats()
  const [etape, setEtape] = useState(0)
  const [roles, setRoles] = useState([])
  const [recherche, setRecherche] = useState('')
  const [resultats, setResultats] = useState([])
  const [personne, setPersonne] = useState(personneVide)
  const [compte, setCompte] = useState(compteVide)
  const [selection, setSelection] = useState([])
  const [secretariatsChoisis, setSecretariatsChoisis] = useState([])
  const [bornes, setBornes] = useState([])
  const [motif, setMotif] = useState('')
  const [enCours, setEnCours] = useState(false)
  const [erreur, setErreur] = useState('')

  const terme = useDebounce(recherche, 300)
  useEffect(() => {
    if (terme.trim().length >= 2) {
      rechercherPersonnes(terme).then(setResultats).catch(() => setResultats([]))
    } else {
      setResultats([])
    }
  }, [terme])

  useEffect(() => { listerRolesCurp().then(setRoles).catch(() => {}) }, [])
  const legacyOptions = useMemo(() => {
    const labels = user?.role_context?.labels || {}
    return Object.entries(labels)
  }, [user])

  const rolesChoisis = selection.map((s) => roles.find((r) => r.code === s.code)).filter(Boolean)
  const sensibleNonSigne = rolesChoisis.some((r) => r.sensible && !selection.find((s) => s.code === r.code)?.sensible_valide)
  const besoinPerimetre = rolesChoisis.some((r) => r.perimetre_defaut === 'SECRETARIAT')
  const incompatibles = useMemo(() => {
    const codes = selection.map((s) => s.code)
    const paires = new Set()
    rolesChoisis.forEach((r) => (r.incompatible_avec || [])
      .forEach((c) => codes.includes(c) && paires.add([r.code, c].sort().join(' ↔ '))))
    return [...paires]
  }, [selection, rolesChoisis])

  const etapesValides = [
    Boolean(personne.resultatSelectionne || personne.nom.trim()),
    Boolean(compte.username && compte.mot_de_passe.length >= 6 && compte.role_legacy),
    selection.length > 0 && incompatibles.length === 0 && !sensibleNonSigne,
    motif.trim().length >= 8,
  ]
  const peutAvancer = etape < 4 ? etapesValides[etape] : true

  const basculerRole = (role) => {
    setSelection((sel) => sel.some((s) => s.code === role.code)
      ? sel.filter((s) => s.code !== role.code)
      : [...sel, { code: role.code, niveau: role.niveau_defaut, sensible_valide: false }])
  }

  const payload = () => ({
    identifiants: {
      username: compte.username.trim(),
      email: compte.email,
      mot_de_passe: compte.mot_de_passe,
      role_legacy: compte.role_legacy,
    },
    personne: personne.resultatSelectionne
      ? { matricule: personne.resultatSelectionne.matricule }
      : { nom: personne.nom, prenoms: personne.prenoms, email: personne.email,
          telephone: personne.telephone, service: personne.service },
    canal: compte.canal,
    motif: motif.trim(),
    roles: selection.map((s) => ({
      role: s.code, niveau: s.niveau,
      sensible_valide: s.sensible_valide,
      perimetres_secretariats: besoinPerimetre ? secretariatsChoisis : [],
      // LOT 5 (L4-02) : bornages Direction/Département, additifs et optionnels.
      perimetres: bornes,
    })),
  })

  const soumettre = async () => {
    setEnCours(true)
    setErreur('')
    try {
      const cree = await creerCompte(payload())
      showToast(`Compte ${cree.username} créé.`, 'success')
      navigate(`/administration/comptes/${cree.id}`)
    } catch (e) {
      setErreur(messageErreur(e, 'La création a échoué.'))
    } finally {
      setEnCours(false)
    }
  }

  return (
    <section>
      <h2 className="h5">Nouveau compte</h2>
      <div className="hab-etapes">
        {ETAPES.map((libelle, i) => (
          <div key={libelle} className={`hab-etape ${i === etape ? 'active' : ''} ${i < etape ? 'terminee' : ''}`}>
            {i + 1}. {libelle}
          </div>
        ))}
      </div>
      <div className="hab-carte">
        {etape === 0 && <EtapePersonne personne={personne} setPersonne={setPersonne}
                                        recherche={recherche} setRecherche={setRecherche} resultats={resultats} />}
        {etape === 1 && <EtapeCompte compte={compte} setCompte={setCompte} legacyOptions={legacyOptions} />}
        {etape === 2 && <EtapeRoles roles={roles} selection={selection} basculerRole={basculerRole}
                                     changerNiveau={(c, n) => setSelection((s) => s.map((x) => x.code === c ? { ...x, niveau: n } : x))}
                                     changerSignature={(c, v) => setSelection((s) => s.map((x) => x.code === c ? { ...x, sensible_valide: v } : x))} />}
        {etape === 3 && <EtapePerimetres secretariats={secretariats} secretariatsChoisis={secretariatsChoisis}
                                          basculerSecretariat={setSecretariatsChoisis} motif={motif}
                                          perimetres={bornes} setPerimetres={setBornes}
                                          setMotif={setMotif} besoinPerimetre={besoinPerimetre} />}
        {etape === 4 && (
          <div className="hab-recap" data-testid="etape-recap">
            <h3 className="h6">5 · Récapitulatif</h3>
            <div><span className="libelle">Personne :</span>
              {personne.resultatSelectionne
                ? `${personne.resultatSelectionne.prenoms} ${personne.resultatSelectionne.nom} (existant)`
                : `${personne.prenoms} ${personne.nom}`}
            </div>
            <div><span className="libelle">Identifiant :</span> {compte.username}</div>
            <div><span className="libelle">Rôle d'accès actuel :</span>
              {user?.role_context?.labels?.[compte.role_legacy] || compte.role_legacy}
            </div>
            <div><span className="libelle">Canal :</span> {compte.canal}</div>
            <div><span className="libelle">Rôles métier :</span>
              {rolesChoisis.map((r) => (
                <span key={r.code} className="badge bg-light text-dark border me-1">
                  {r.libelle}{r.sensible && <BadgeSensible />} ({selection.find((s) => s.code === r.code)?.niveau})
                </span>
              ))}
            </div>
            {incompatibles.length > 0 && <p className="text-danger">Incompatibilités : {incompatibles.join(', ')}</p>}
            {sensibleNonSigne && <p className="text-danger">Un rôle sensible nécessite la seconde signature.</p>}
            <div><span className="libelle">Motif :</span> {motif}</div>
          </div>
        )}
        {erreur && <p className="text-danger mt-2" data-testid="assistant-erreur">{erreur}</p>}
      </div>
      <div className="d-flex justify-content-between">
        <button className="btn btn-secondary" disabled={etape === 0 || enCours}
                onClick={() => setEtape((e) => e - 1)}>Précédent</button>
        {etape < 4 ? (
          <button className="btn btn-success" disabled={!peutAvancer} data-testid="bouton-suivant"
                  onClick={() => setEtape((e) => e + 1)}>Suivant</button>
        ) : (
          <button className="btn btn-success" disabled={enCours || etapesValides.some((v) => !v)} data-testid="bouton-creer"
                  onClick={soumettre}>{enCours ? 'Création…' : 'Créer le compte'}</button>
        )}
      </div>
    </section>
  )
}
