/** Derogations — liste, proposition bornée, révocation motivée (U4). */
import { useEffect, useState } from 'react'
import {
  listerComptes, listerDerogations, creerDerogation, revoquerDerogation, messageErreur,
} from '@/services/habilitations'
import { useToast } from '@/context/ToastContext'
import { EnChargement } from './partages'
import MotifModal from './MotifModal'
import './habilitations.css'

const formVide = { compte: '', permission: '', sens: 'OCTROI', motif: '', date_fin: '' }

export default function Derogations() {
  const { showToast } = useToast()
  const [comptes, setComptes] = useState([])
  const [donnees, setDonnees] = useState(null)
  const [chargement, setChargement] = useState(true)
  const [erreurChargement, setErreurChargement] = useState('')
  const [form, setForm] = useState(formVide)
  const [aRevoquer, setARevoquer] = useState(null)

  const charger = async () => {
    setChargement(true)
    setErreurChargement('')
    try {
      const [listeComptes, listeDerogations] = await Promise.all([
        listerComptes({ page_size: 200 }), listerDerogations(),
      ])
      setComptes(listeComptes.results || [])
      setDonnees(listeDerogations)
    } catch (e) {
      setErreurChargement(messageErreur(e, 'Chargement des dérogations impossible.'))
    } finally {
      setChargement(false)
    }
  }
  useEffect(() => { charger() }, [])

  const maj = (k, v) => setForm((f) => ({ ...f, [k]: v }))
  const creer = async (e) => {
    e.preventDefault()
    try {
      await creerDerogation({
        compte: Number(form.compte), permission: form.permission,
        sens: form.sens, motif: form.motif,
        date_fin: form.sens === 'OCTROI' ? form.date_fin : null,
      })
      showToast('Dérogation proposée.', 'success')
      setForm(formVide)
      charger()
    } catch (erreur) {
      showToast(messageErreur(erreur), 'error')
    }
  }
  const confirmerRevocation = async (motif) => {
    await revoquerDerogation(aRevoquer.id, motif)
    showToast('Dérogation révoquée.', 'success')
    setARevoquer(null)
    charger()
  }

  if (chargement) return <EnChargement message="Chargement des dérogations…" />
  if (erreurChargement) return (
    <section data-testid="ecran-derogations">
      <div className="hab-carte hab-avertissement" role="alert" data-testid="derogations-erreur">
        <p>{erreurChargement}</p>
        <button type="button" className="btn btn-sm btn-outline-primary" onClick={charger}>Réessayer</button>
      </div>
    </section>
  )
  return (
    <section data-testid="ecran-derogations">
      <div className="hab-carte">
        <h2 className="h5">Dérogations de permission</h2>
        <p className="hab-muted">
          Octroi exceptionnel temporaire ou retrait ciblé. Le circuit complet d'instruction et la
          double signature sont ouverts à l'unité U5 ; toute proposition reste tracée.
        </p>
        <form className="row g-2" onSubmit={creer} data-testid="form-derogation">
          <div className="col-md-3">
            <select className="form-select" required value={form.compte} onChange={(e) => maj('compte', e.target.value)}>
              <option value="">Compte…</option>
              {comptes.map((c) => <option key={c.id} value={c.id}>{c.username}</option>)}
            </select>
          </div>
          <div className="col-md-3">
            <input className="form-control" placeholder="Code permission (ex. evaluations.note.saisir)"
                   value={form.permission} data-testid="input-permission"
                   onChange={(e) => maj('permission', e.target.value)} required />
          </div>
          <div className="col-md-2">
            <select className="form-select" value={form.sens} onChange={(e) => maj('sens', e.target.value)}>
              <option value="OCTROI">Octroi</option>
              <option value="RETRAIT">Retrait</option>
            </select>
          </div>
          <div className="col-md-2">
            <input type="date" className="form-control" required={form.sens === 'OCTROI'}
                   value={form.date_fin} onChange={(e) => maj('date_fin', e.target.value)}
                   title="Échéance obligatoire pour un octroi" />
          </div>
          <div className="col-md-2">
            <input className="form-control" placeholder="Motif" value={form.motif}
                   onChange={(e) => maj('motif', e.target.value)} required />
          </div>
          <div className="col-12">
            <button className="btn btn-success btn-sm" data-testid="bouton-creer-derogation">Proposer la dérogation</button>
          </div>
        </form>
      </div>
      <div className="hab-carte">
        <table className="hab-table">
          <thead><tr><th>Compte</th><th>Sens</th><th>Permission</th><th>Échéance</th><th>Statut</th><th></th></tr></thead>
          <tbody>
            {donnees.results.map((d) => (
              <tr key={d.id}>
                <td>{d.username}</td>
                <td>{d.sens === 'OCTROI' ? 'Octroi' : 'Retrait'}{d.sensible ? <span className="hab-badge-sensible ms-1">Critique</span> : ''}</td>
                <td><code>{d.permission}</code></td>
                <td>{d.date_fin || '—'}</td>
                <td>{d.statut}</td>
                <td>{['PROPOSEE', 'ACTIVE'].includes(d.statut) && (
                  <button className="btn btn-sm btn-outline-danger"
                          onClick={() => setARevoquer(d)}>Révoquer</button>)}</td>
              </tr>
            ))}
            {donnees.results.length === 0 && <tr><td colSpan="6" className="hab-muted text-center py-3">Aucune dérogation.</td></tr>}
          </tbody>
        </table>
      </div>
      {aRevoquer && (
        <MotifModal titre="Révoquer la dérogation"
                    action={`Révoquer ${aRevoquer.sens === 'OCTROI' ? "l'octroi" : 'le retrait'} de ${aRevoquer.permission}`}
                    consequences="La permission retrouve immédiatement le comportement normal des rôles du compte."
                    onConfirmer={confirmerRevocation} onAnnuler={() => setARevoquer(null)} />
      )}
    </section>
  )
}
