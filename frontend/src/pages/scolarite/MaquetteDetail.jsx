import React, { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import api from '../../services/api'
import { canActScolarite } from '../../utils/roles'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'

export default function MaquetteDetail() {
  const { id } = useParams()
  const { user } = useAuth()
  const toast = useToast()
  const peutAgir = canActScolarite(user)

  const [maquette, setMaquette] = useState(null)
  const [journal, setJournal] = useState([])
  const [enCours, setEnCours] = useState(false)
  const [formUe, setFormUe] = useState({ semestre_id: '', code: '', intitule: '', credits: 0 })
  const [semestres, setSemestres] = useState([])
  const [formEcue, setFormEcue] = useState({ ue_id: '', code: '', intitule: '', credits: 0, coefficient: 1 })

  const charger = useCallback(async () => {
    try {
      const [res, jr] = await Promise.all([
        api.get(`/scolarite/maquettes/${id}/`),
        api.get(`/scolarite/maquettes/${id}/journal/`),
      ])
      setMaquette(res.data)
      setJournal(jr.data)
    } catch (err) {
      toast.showToast(err.response?.data?.error || 'Chargement impossible.', 'error')
    }
  }, [id, toast])

  useEffect(() => { charger() }, [charger])

  useEffect(() => {
    if (!peutAgir || maquette?.statut !== 'BROUILLON') return
    api.get('/scolarite/ref/semestres/')
      .then((res) => setSemestres(res.data))
      .catch(() => {})
  }, [peutAgir, maquette?.statut])

  const brouillon = maquette?.statut === 'BROUILLON'
  const editable = brouillon && peutAgir

  const actionWorkflow = async (verbe, confirmation) => {
    if (confirmation && !window.confirm(confirmation)) return
    setEnCours(true)
    try {
      const res = await api.post(`/scolarite/maquettes/${id}/${verbe}/`, {})
      toast.showToast('Opération effectuée.')
      setMaquette(res.data)
      charger()
    } catch (err) {
      const problemes = err.response?.data?.problemes
      toast.showToast(problemes?.length ? problemes.join(' ') : (err.response?.data?.error || 'Action impossible.'), 'error')
    } finally {
      setEnCours(false)
    }
  }

  const cloner = async () => {
    if (!window.confirm('Créer une nouvelle version (clonage) ?')) return
    setEnCours(true)
    try {
      const res = await api.post(`/scolarite/maquettes/${id}/cloner/`, {})
      toast.showToast(`Version v${res.data.version} créée en brouillon.`)
      window.location.href = `/scolarite/maquettes/${res.data.id}`
    } catch (err) {
      toast.showToast(err.response?.data?.error || 'Clonage impossible.', 'error')
    } finally {
      setEnCours(false)
    }
  }

  const ajouterUe = async (e) => {
    e.preventDefault()
    setEnCours(true)
    try {
      await api.post(`/scolarite/maquettes/${id}/ues/`, {
        ...formUe,
        semestre_id: Number(formUe.semestre_id),
        credits: Number(formUe.credits) || 0,
      })
      toast.showToast('UE ajoutée.')
      setFormUe({ semestre_id: '', code: '', intitule: '', credits: 0 })
      charger()
    } catch (err) {
      toast.showToast(err.response?.data?.error || 'Ajout impossible.', 'error')
    } finally {
      setEnCours(false)
    }
  }

  const ajouterEcue = async (e) => {
    e.preventDefault()
    setEnCours(true)
    try {
      await api.post(`/scolarite/ues/${formEcue.ue_id}/ecues/`, {
        code: formEcue.code, intitule: formEcue.intitule,
        credits: Number(formEcue.credits) || 0, coefficient: formEcue.coefficient,
      })
      toast.showToast('ECUE ajoutée.')
      setFormEcue({ ue_id: '', code: '', intitule: '', credits: 0, coefficient: 1 })
      charger()
    } catch (err) {
      toast.showToast(err.response?.data?.error || 'Ajout impossible.', 'error')
    } finally {
      setEnCours(false)
    }
  }

  const supprimerEcue = async (ecueId) => {
    if (!window.confirm("Archiver cette ECUE ? Elle ne pourra plus entrer dans une nouvelle maquette.")) return
    try {
      await api.delete(`/scolarite/ecues/${ecueId}/?mode=archive`)
      toast.showToast('ECUE archivée.')
      charger()
    } catch (err) {
      toast.showToast(err.response?.data?.error || 'Suppression impossible.', 'error')
    }
  }

  if (!maquette) {
    return <div className="container-fluid py-4"><div className="spinner-border" /></div>
  }

  const semestresMap = {}
  for (const ue of maquette.unites_enseignement) {
    const cle = `${ue.semestre.id}`
    semestresMap[cle] = semestresMap[cle] || { semestre: ue.semestre, ues: [] }
    semestresMap[cle].ues.push(ue)
  }

  return (
    <div className="container-fluid py-4">
      <div className="d-flex justify-content-between align-items-start mb-3 flex-wrap gap-2">
        <div>
          <h1 className="h4 mb-1">{maquette.libelle || maquette.ref_formation}</h1>
          <div className="text-muted">
            {maquette.niveau} · {maquette.annee_academique} · v{maquette.version}
            {' '}· <span className="badge text-bg-secondary">{maquette.statut}</span>
            {' '}· {maquette.credits_total} crédits · {maquette.volume_horaire_total} h
          </div>
        </div>
        <Link className="btn btn-outline-secondary btn-sm" to="/scolarite/maquettes">← Retour</Link>
      </div>

      {maquette.problemes_coherence?.length > 0 && (
        <div className="alert alert-warning">
          <strong>Contrôles de cohérence :</strong>
          <ul className="mb-0 mt-1">
            {maquette.problemes_coherence.map((p, i) => <li key={i}>{p}</li>)}
          </ul>
        </div>
      )}

      {peutAgir && (
        <div className="btn-group mb-3">
          {brouillon && (
            <button className="btn btn-info" disabled={enCours}
                    onClick={() => actionWorkflow('valider', 'Valider cette maquette (contenu gelé) ?')}>
              <i className="bi bi-check2-circle me-1"></i>Valider
            </button>
          )}
          {maquette.statut === 'VALIDEE' && (
            <button className="btn btn-success" disabled={enCours}
                    onClick={() => actionWorkflow('activer', 'Activer cette maquette (immuable) ?')}>
              <i className="bi bi-play-circle me-1"></i>Activer
            </button>
          )}
          {maquette.statut === 'ACTIVE' && (
            <button className="btn btn-dark" disabled={enCours}
                    onClick={() => actionWorkflow('archiver', 'Archiver cette maquette ?')}>
              <i className="bi bi-archive me-1"></i>Archiver
            </button>
          )}
          {maquette.statut !== 'BROUILLON' && (
            <button className="btn btn-secondary" disabled={enCours} onClick={cloner}>
              <i className="bi bi-copy me-1"></i>Cloner en nouvelle version
            </button>
          )}
        </div>
      )}

      {Object.values(semestresMap).map(({ semestre, ues }) => (
        <div className="card mb-3" key={semestre.id}>
          <div className="card-header">{semestre.libelle}</div>
          <div className="card-body">
            {ues.map((ue) => (
              <div className="mb-3" key={ue.id}>
                <div className="fw-semibold">
                  {ue.code} — {ue.intitule} <span className="badge text-bg-light">{ue.credits} crédits</span>
                  {' '}<span className="badge text-bg-light">{ue.caractere}</span>
                </div>
                <ul className="list-unstyled ms-3 mb-1">
                  {ue.ecues.map((ecue) => (
                    <li key={ecue.id}>
                      {ecue.code} — {ecue.intitule} · {ecue.credits} cr. · coeff. {ecue.coefficient}
                      {' '}· {ecue.volume_total} h
                      {ecue.archive && <span className="badge text-bg-warning ms-1">archivée</span>}
                      {editable && !ecue.archive && (
                        <button className="btn btn-link btn-sm text-danger p-0 ms-2"
                                onClick={() => supprimerEcue(ecue.id)}>archiver</button>
                      )}
                    </li>
                  ))}
                </ul>
                {editable && (
                  <form className="row g-1 ms-3 align-items-center" onSubmit={ajouterEcue}>
                    <div className="col-auto">
                      <input className="form-control form-control-sm" placeholder="Code ECUE" required
                             onFocus={() => setFormEcue({ ...formEcue, ue_id: ue.id })}
                             value={formEcue.ue_id === ue.id ? formEcue.code : ''}
                             onChange={(e) => setFormEcue({ ...formEcue, ue_id: ue.id, code: e.target.value })} />
                    </div>
                    <div className="col-auto">
                      <input className="form-control form-control-sm" placeholder="Intitulé" required
                             onFocus={() => setFormEcue({ ...formEcue, ue_id: ue.id })}
                             value={formEcue.ue_id === ue.id ? formEcue.intitule : ''}
                             onChange={(e) => setFormEcue({ ...formEcue, ue_id: ue.id, intitule: e.target.value })} />
                    </div>
                    <div className="col-auto">
                      <input type="number" min="0" className="form-control form-control-sm" placeholder="Cr." required
                             onFocus={() => setFormEcue({ ...formEcue, ue_id: ue.id })}
                             value={formEcue.ue_id === ue.id ? formEcue.credits : ''}
                             onChange={(e) => setFormEcue({ ...formEcue, ue_id: ue.id, credits: e.target.value })} />
                    </div>
                    <div className="col-auto">
                      <button className="btn btn-sm btn-outline-primary">+ ECUE</button>
                    </div>
                  </form>
                )}
              </div>
            ))}
          </div>
        </div>
      ))}

      {editable && (
        <div className="card mb-3">
          <div className="card-body">
            <h2 className="h6 card-title"><i className="bi bi-plus-circle me-1"></i>Ajouter une unité d'enseignement</h2>
            <form className="row g-2" onSubmit={ajouterUe}>
              <div className="col-md-3">
                <select className="form-select" required value={formUe.semestre_id}
                        onChange={(e) => setFormUe({ ...formUe, semestre_id: e.target.value })}>
                  <option value="">Semestre…</option>
                  {semestres.map((s) => <option key={s.id} value={s.id}>{s.libelle}</option>)}
                </select>
              </div>
              <div className="col-md-2">
                <input className="form-control" placeholder="Code UE" required value={formUe.code}
                       onChange={(e) => setFormUe({ ...formUe, code: e.target.value })} />
              </div>
              <div className="col-md-4">
                <input className="form-control" placeholder="Intitulé" required value={formUe.intitule}
                       onChange={(e) => setFormUe({ ...formUe, intitule: e.target.value })} />
              </div>
              <div className="col-md-1">
                <input type="number" min="0" className="form-control" placeholder="Cr." required
                       value={formUe.credits} onChange={(e) => setFormUe({ ...formUe, credits: e.target.value })} />
              </div>
              <div className="col-md-2">
                <button className="btn btn-primary w-100" disabled={enCours}>Ajouter</button>
              </div>
            </form>
          </div>
        </div>
      )}

      <div className="card">
        <div className="card-header"><i className="bi bi-clock-history me-1"></i>Historique des validations</div>
        <ul className="list-group list-group-flush">
          {journal.length === 0 ? (
            <li className="list-group-item text-muted">Aucune entrée.</li>
          ) : journal.map((j, i) => (
            <li className="list-group-item d-flex justify-content-between" key={i}>
              <span><span className="badge text-bg-light me-2">{j.action}</span>{j.utilisateur || '—'}</span>
              <small className="text-muted">{new Date(j.horodatage).toLocaleString('fr-FR')}</small>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
