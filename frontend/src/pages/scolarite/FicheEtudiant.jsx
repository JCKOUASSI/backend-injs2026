import React, { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useToast } from '../../context/ToastContext'
import StatutBadge from '../../components/scolarite/StatutBadge'
import ConfirmModal from '../../components/ConfirmModal'
import {
  affecterGroupe,
  analyserPasserelle,
  genererPedagogie,
  getAffectations,
  getEffectifsGroupes,
  getEtudiant,
  getEvenements,
  getFormationsOperationnelles,
  getPedagogie,
  messageErreur,
  retirerEcue,
  synchroniserPasserelle,
} from '../../services/scolarite'

function Section({ titre, action, children }) {
  return (
    <div className="card mb-3">
      <div className="card-header d-flex justify-content-between align-items-center">
        <strong>{titre}</strong>
        {action}
      </div>
      <div className="card-body">{children}</div>
    </div>
  )
}

function Identite({ etudiant }) {
  const champs = [
    ['Matricule', etudiant.matricule],
    ['Nom et prénoms', etudiant.nom_complet],
    ['Sexe', etudiant.sexe || '—'],
    ['Date de naissance', etudiant.date_naissance || '—'],
    ['Lieu de naissance', etudiant.lieu_naissance || '—'],
    ['Email', etudiant.email || '—'],
    ['Téléphone', etudiant.telephone || '—'],
    ['Statut', etudiant.statut || '—'],
    ['Première inscription', etudiant.date_premiere_inscription || '—'],
  ]
  return (
    <div className="row g-3">
      {champs.map(([libelle, valeur]) => (
        <div className="col-md-4" key={libelle}>
          <small className="text-muted d-block">{libelle}</small>
          <span>{valeur}</span>
        </div>
      ))}
    </div>
  )
}

function Pedagogie({ inscription, onChange }) {
  const { showToast } = useToast()
  const [donnees, setDonnees] = useState(null)
  const [chargement, setChargement] = useState(true)
  const [action, setAction] = useState(false)
  // ECUE dont le retrait est en attente de confirmation (§10.9, corrigé au
  // LOT 45 : cohérence avec les autres actions destructrices confirmées).
  const [aRetirer, setARetirer] = useState(null)

  const charger = useCallback(async () => {
    setChargement(true)
    try {
      const res = await getPedagogie(inscription.id)
      setDonnees(res.data)
    } catch (err) {
      showToast(messageErreur(err, 'Chargement du programme impossible'), 'error')
    } finally {
      setChargement(false)
    }
  }, [inscription.id, showToast])

  useEffect(() => { charger() }, [charger])

  const generer = async () => {
    setAction(true)
    try {
      const res = await genererPedagogie(inscription.id, {})
      showToast(`${res.data.creees} enseignement(s) ajouté(s)`)
      await charger()
      onChange?.()
    } catch (err) {
      showToast(messageErreur(err, 'Génération impossible'), 'error')
    } finally {
      setAction(false)
    }
  }

  const retirer = async (ligne) => {
    try {
      await retirerEcue(ligne.id)
      showToast(`${ligne.ecue_code} retirée`)
      await charger()
    } catch (err) {
      showToast(messageErreur(err, 'Retrait impossible'), 'error')
    }
  }

  const recap = donnees?.recapitulatif
  const lignes = donnees?.lignes || []

  return (
    <>
    <Section
      titre="Programme pédagogique"
      action={
        <button className="btn btn-sm btn-outline-primary" disabled={action} onClick={generer}>
          {action && <span className="spinner-border spinner-border-sm me-1"></span>}
          Générer depuis la maquette
        </button>
      }
    >
      {chargement ? (
        <div className="text-center py-3"><div className="spinner-border spinner-border-sm"></div></div>
      ) : (
        <>
          {recap && (
            <div className="d-flex gap-4 mb-3 flex-wrap">
              <div><small className="text-muted d-block">Enseignements</small><strong>{recap.total_ecues}</strong></div>
              <div><small className="text-muted d-block">Crédits ECTS</small><strong>{recap.total_credits}</strong></div>
              {Object.entries(recap.par_semestre || {}).map(([libelle, valeurs]) => (
                <div key={libelle}>
                  <small className="text-muted d-block">{libelle}</small>
                  <strong>{valeurs.credits} crédits</strong>
                  <span className="text-muted small"> · {valeurs.volume_horaire} h</span>
                </div>
              ))}
            </div>
          )}
          <div className="table-responsive">
            <table className="table table-sm align-middle">
              <thead>
                <tr>
                  <th>Semestre</th><th>UE</th><th>ECUE</th><th>Type</th>
                  <th>Crédits</th><th>Volume</th><th>Groupe</th><th>Origine</th><th></th>
                </tr>
              </thead>
              <tbody>
                {lignes.map((ligne) => (
                  <tr key={ligne.id}>
                    <td>{ligne.semestre}</td>
                    <td><code>{ligne.ue_code}</code></td>
                    <td>{ligne.ecue_code} — {ligne.ecue_intitule}</td>
                    <td>{ligne.type_enseignement}</td>
                    <td>{ligne.credits}</td>
                    <td>{ligne.volume_horaire} h</td>
                    <td>{ligne.groupe || <span className="text-muted">—</span>}</td>
                    <td>
                      <span className={`badge bg-${ligne.origine === 'MANUELLE' ? 'warning' : 'light text-dark'}`}>
                        {ligne.origine === 'MANUELLE' ? 'Manuel' : 'Maquette'}
                      </span>
                    </td>
                    <td className="text-end">
                      <button className="btn btn-sm btn-outline-danger" onClick={() => setARetirer(ligne)}>
                        Retirer
                      </button>
                    </td>
                  </tr>
                ))}
                {lignes.length === 0 && (
                  <tr>
                    <td colSpan={9} className="text-muted text-center py-3">
                      Aucun enseignement. Générez le programme depuis la maquette.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}
    </Section>
    {aRetirer && (
      <ConfirmModal
        message={`Retirer « ${aRetirer.ecue_code} — ${aRetirer.ecue_intitule} » du programme pédagogique ?`}
        detail="L'enseignement sera dissocié de cette fiche ; il pourra être régénéré depuis la maquette."
        confirmLabel="Retirer"
        onConfirm={async () => {
          const ligne = aRetirer
          setARetirer(null)
          await retirer(ligne)
        }}
        onCancel={() => setARetirer(null)}
      />
    )}
    </>
  )
}

function Groupes({ inscription }) {
  const { showToast } = useToast()
  const [affectations, setAffectations] = useState([])
  const [groupes, setGroupes] = useState([])
  const [choix, setChoix] = useState('')
  const [action, setAction] = useState(false)

  const charger = useCallback(async () => {
    const [affectationsRes, groupesRes] = await Promise.all([
      getAffectations(inscription.id),
      getEffectifsGroupes({
        annee_academique_id: inscription.annee_academique_id,
        ref_formation_id: inscription.ref_formation_id,
        niveau_id: inscription.niveau_id,
      }).catch(() => ({ data: [] })),
    ])
    setAffectations(affectationsRes.data || [])
    setGroupes(groupesRes.data || [])
  }, [inscription])

  useEffect(() => { charger() }, [charger])

  const affecter = async () => {
    if (!choix) return
    setAction(true)
    try {
      await affecterGroupe(inscription.id, { groupe_id: choix })
      showToast('Affectation enregistrée')
      setChoix('')
      await charger()
    } catch (err) {
      showToast(messageErreur(err, 'Affectation refusée'), 'error')
    } finally {
      setAction(false)
    }
  }

  const active = affectations.find((a) => a.active)

  return (
    <Section titre="Groupe pédagogique">
      <div className="mb-3">
        <small className="text-muted d-block">Groupe actuel</small>
        {active ? <strong>{active.groupe}</strong> : <span className="text-muted">Non affecté</span>}
      </div>
      <div className="row g-2 align-items-end mb-3">
        <div className="col-md-5">
          <label className="form-label">Affecter à un groupe</label>
          <select className="form-select" value={choix} onChange={(e) => setChoix(e.target.value)}>
            <option value="">Choisir…</option>
            {groupes.map((g) => (
              <option key={g.id} value={g.id} disabled={g.places_restantes === 0}>
                {g.nom} — {g.effectif}{g.capacite_max ? `/${g.capacite_max}` : ''}
                {g.places_restantes === 0 ? ' (complet)' : ''}
              </option>
            ))}
          </select>
        </div>
        <div className="col-md-3">
          <button className="btn btn-primary" disabled={!choix || action} onClick={affecter}>
            Affecter
          </button>
        </div>
      </div>
      {affectations.length > 1 && (
        <>
          <small className="text-muted d-block mb-1">Historique</small>
          <ul className="list-unstyled small mb-0">
            {affectations.filter((a) => !a.active).map((a) => (
              <li key={a.id}>
                {a.groupe} — du {a.date_debut} au {a.date_fin || '…'}
                {a.motif && <span className="text-muted"> · {a.motif}</span>}
              </li>
            ))}
          </ul>
        </>
      )}
    </Section>
  )
}

function Passerelle({ inscription }) {
  const { showToast } = useToast()
  const [formations, setFormations] = useState([])
  const [choix, setChoix] = useState('')
  const [analyse, setAnalyse] = useState(null)
  const [action, setAction] = useState(false)

  useEffect(() => {
    getFormationsOperationnelles()
      .then((res) => setFormations(Array.isArray(res.data) ? res.data : (res.data?.results || [])))
      .catch(() => setFormations([]))
  }, [])

  const analyser = async () => {
    setAction(true)
    try {
      const res = await analyserPasserelle(inscription.id, { formation_id: choix })
      setAnalyse(res.data)
    } catch (err) {
      showToast(messageErreur(err, 'Analyse impossible'), 'error')
    } finally {
      setAction(false)
    }
  }

  const synchroniser = async () => {
    setAction(true)
    try {
      const res = await synchroniserPasserelle(inscription.id, { formation_id: choix })
      showToast(`${res.data.creees} inscription(s) au module créée(s)`)
      setAnalyse(null)
    } catch (err) {
      showToast(messageErreur(err, 'Synchronisation impossible'), 'error')
    } finally {
      setAction(false)
    }
  }

  return (
    <Section titre="Rattachement aux cours">
      <p className="text-muted small">
        Inscrit l’étudiant aux modules opérationnels correspondant à son programme.
        L’opération n’ajoute que ce qui manque et ne retire jamais une inscription existante.
      </p>
      <div className="row g-2 align-items-end">
        <div className="col-md-5">
          <label className="form-label">Formation opérationnelle</label>
          <select className="form-select" value={choix} onChange={(e) => { setChoix(e.target.value); setAnalyse(null) }}>
            <option value="">Choisir…</option>
            {formations.map((f) => <option key={f.id} value={f.id}>{f.formation}</option>)}
          </select>
        </div>
        <div className="col-md-4">
          <div className="btn-group">
            <button className="btn btn-outline-secondary" disabled={!choix || action} onClick={analyser}>
              Prévisualiser
            </button>
            <button className="btn btn-primary" disabled={!choix || action} onClick={synchroniser}>
              Synchroniser
            </button>
          </div>
        </div>
      </div>

      {analyse && (
        <div className="mt-3">
          <div className="alert alert-info mb-2">
            {analyse.a_creer.length} inscription(s) à créer, {analyse.existantes.length} déjà en place.
          </div>
          {analyse.a_creer.length > 0 && (
            <ul className="small mb-2">
              {analyse.a_creer.map((item, index) => (
                <li key={index}>{item.ecue} → {item.module}</li>
              ))}
            </ul>
          )}
          {analyse.non_rapprochees.length > 0 && (
            <div className="alert alert-warning mb-0">
              <strong>Non rapprochés</strong>
              <ul className="small mb-0 mt-1">
                {analyse.non_rapprochees.map((item, index) => (
                  <li key={index}>{item.ecue} — {item.motif}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </Section>
  )
}

export default function FicheEtudiant() {
  const { id } = useParams()
  const { showToast } = useToast()
  const [etudiant, setEtudiant] = useState(null)
  const [evenements, setEvenements] = useState([])
  const [loading, setLoading] = useState(true)

  const charger = useCallback(async () => {
    setLoading(true)
    try {
      const [etudiantRes, evenementsRes] = await Promise.all([
        getEtudiant(id),
        getEvenements(id).catch(() => ({ data: [] })),
      ])
      setEtudiant(etudiantRes.data)
      setEvenements(evenementsRes.data || [])
    } catch (err) {
      showToast(messageErreur(err, 'Fiche introuvable'), 'error')
    } finally {
      setLoading(false)
    }
  }, [id, showToast])

  useEffect(() => { charger() }, [charger])

  if (loading) return <div className="loading"><div className="spinner"></div></div>
  if (!etudiant) return <div className="alert alert-danger">Fiche étudiant introuvable.</div>

  const courante = etudiant.inscription_courante

  return (
    <div>
      <div className="d-flex justify-content-between align-items-center mb-3 flex-wrap gap-2">
        <div>
          <h4 className="mb-0">{etudiant.nom_complet}</h4>
          <small className="text-muted"><code>{etudiant.matricule}</code></small>
        </div>
        <Link to="/scolarite/inscriptions" className="btn btn-sm btn-outline-secondary">
          <i className="bi bi-arrow-left me-1"></i>Retour
        </Link>
      </div>

      <Section titre="Identité"><Identite etudiant={etudiant} /></Section>

      <Section titre="Parcours administratif">
        <div className="table-responsive">
          <table className="table table-sm align-middle mb-0">
            <thead>
              <tr><th>Année</th><th>Formation</th><th>Niveau</th><th>Type</th><th>Statut</th></tr>
            </thead>
            <tbody>
              {etudiant.inscriptions.map((i) => (
                <tr key={i.id}>
                  <td>{i.annee_academique}</td>
                  <td>{i.ref_formation}</td>
                  <td>{i.niveau}</td>
                  <td><small>{i.type_inscription_libelle}</small></td>
                  <td><StatutBadge statut={i.statut} libelle={i.statut_libelle} /></td>
                </tr>
              ))}
              {etudiant.inscriptions.length === 0 && (
                <tr><td colSpan={5} className="text-muted">Aucune inscription.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </Section>

      {courante ? (
        <>
          <Groupes inscription={courante} />
          <Pedagogie inscription={courante} />
          <Passerelle inscription={courante} />
        </>
      ) : (
        <div className="alert alert-warning">
          Aucune inscription validée pour cet étudiant : le programme pédagogique,
          l’affectation de groupe et le rattachement aux cours seront disponibles
          une fois l’inscription validée.
        </div>
      )}

      <Section titre="Chronologie">
        {evenements.length === 0 ? (
          <p className="text-muted mb-0">Aucun événement enregistré.</p>
        ) : (
          <ul className="list-unstyled mb-0">
            {evenements.map((e) => (
              <li key={e.id} className="mb-2">
                <span className="badge bg-light text-dark me-2">{e.date_evenement}</span>
                <strong>{e.type_libelle}</strong>
                {e.ancienne_valeur && <span className="text-muted"> — de {e.ancienne_valeur}</span>}
                {e.nouvelle_valeur && <span className="text-muted"> vers {e.nouvelle_valeur}</span>}
                {e.commentaire && <div className="text-muted small ms-5">{e.commentaire}</div>}
              </li>
            ))}
          </ul>
        )}
      </Section>
    </div>
  )
}
