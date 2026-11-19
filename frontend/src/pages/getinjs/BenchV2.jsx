import { useState } from 'react'
import api from '../../services/api'

const CHAMPS = [
  ['annee_id', 'Année BENCHMARK', 'number'], ['groupe_id', 'Groupe fictif', 'number'],
  ['ecue_id', 'ECUE fictif (0 si absent)', 'number'], ['ordinal', 'Ordinal', 'number'],
  ['duree_minutes', 'Durée (minutes)', 'number'], ['effectif', 'Effectif fictif', 'number'],
  ['formateur_id', 'Formateur fictif', 'number'], ['revision', 'Révision calendrier', 'number'],
  ['jour', 'Date ciblée', 'date'], ['source_document', 'Source fictive de test', 'text'],
]
const DEFAUT = { annee_id: '', groupe_id: '', ecue_id: '0', type_seance: 'CM',
  ordinal: '1', duree_minutes: '120', effectif: '', formateur_id: '', revision: '1',
  jour: '', source_document: '', source_confirmee: false }

/** Écran de démonstration local : aucun chemin vers une campagne réelle. */
export default function BenchV2() {
  const [form, setForm] = useState(DEFAUT)
  const [decision, setDecision] = useState(null)
  const [erreur, setErreur] = useState('')
  const [attente, setAttente] = useState(false)
  const [executionId, setExecutionId] = useState('')
  const [execution, setExecution] = useState(null)
  const changer = (cle, valeur) => { setForm((avant) => ({ ...avant, [cle]: valeur })); setDecision(null) }
  const payload = () => Object.fromEntries(Object.entries(form).map(([cle, valeur]) =>
    cle === 'source_confirmee' || cle === 'jour' || cle === 'source_document'
      ? [cle, valeur] : [cle, Number(valeur)]))
  const simuler = async (e) => {
    e.preventDefault(); setAttente(true); setErreur(''); setDecision(null)
    try {
      const rep = await api.post('/edts/v2/bench/simuler-ligne/', payload())
      setDecision(rep.data?.decision ?? rep.decision)
    } catch (err) { setErreur(err.response?.data?.code || err.message) }
    finally { setAttente(false) }
  }
  const placer = async () => {
    if (decision?.statut !== 'PLACEE' || !window.confirm('Placer cette occurrence FICTIVE en brouillon ? Aucune publication ne sera effectuée.')) return
    setAttente(true); setErreur('')
    try {
      const rep = await api.post('/edts/v2/bench/placer-ligne/', {
        ...payload(), creneau_id: decision.creneau_id, salle_id: decision.salle_id,
      })
      setDecision(rep.data?.decision ?? rep.decision)
    } catch (err) { setErreur(err.response?.data?.code || err.message) }
    finally { setAttente(false) }
  }
  const lireEtat = async () => {
    setErreur(''); setExecution(null)
    try {
      const rep = await api.get(`/edts/v2/bench/executions/${Number(executionId)}/`)
      setExecution(rep.data ?? rep)
    } catch (err) { setErreur(err.response?.data?.code || err.message) }
  }
  return <main className="container py-4">
    <h1>Prototype v2 — données fictives uniquement</h1>
    <p role="status">Écran local de test BENCHMARK. Source saisie non institutionnelle. Publication v2 bloquée jusqu’au rapprochement QR attesté. Aucun worker n’est lancé par cet écran.</p>
    <form onSubmit={simuler}>
      <div className="row g-2">
        {CHAMPS.map(([cle, label, type]) => <label key={cle} className="col-md-4">{label}
          <input className="form-control" type={type} value={form[cle]} required={cle !== 'source_document'}
            onChange={(e) => changer(cle, e.target.value)} />
        </label>)}
        <label className="col-md-4">Type de séance
          <select className="form-select" value={form.type_seance} onChange={(e) => changer('type_seance', e.target.value)}>
            {['CM', 'TD', 'TP', 'EXAM'].map((v) => <option key={v}>{v}</option>)}
          </select>
        </label>
        <label className="col-md-8"><input type="checkbox" checked={form.source_confirmee}
          onChange={(e) => changer('source_confirmee', e.target.checked)} /> Je confirme uniquement la source FICTIVE pour cet essai local (non officielle).</label>
      </div>
      <button type="submit" disabled={attente}>Simuler sans écriture</button>
    </form>
    {erreur && <div role="alert">Refus : {erreur}</div>}
    {decision && <section aria-label="Décision v2">
      <p>{decision.statut} — {decision.code} — {decision.jour || 'aucune date'}</p>
      {decision.statut === 'PLACEE' && <>
        <p>Créneau #{decision.creneau_id}, salle #{decision.salle_id}. Score souple : {decision.score_souple}.</p>
        <p>Alternatives : {decision.alternatives?.map((a) => a.join(' / ')).join(' ; ') || 'aucune'}</p>
        <button type="button" disabled={attente} onClick={placer}>Confirmer le placement fictif en brouillon</button>
      </>}
    </section>}
    <section><h2>Suivi agrégé d’une exécution BENCHMARK</h2>
      <label>Identifiant d’exécution <input type="number" min="1" value={executionId}
        onChange={(e) => setExecutionId(e.target.value)} /></label>
      <button type="button" disabled={!executionId || attente} onClick={lireEtat}>Lire l’état</button>
      {execution && <p>{execution.statut} — {execution.lignes_traitees} traitées, {execution.lignes_placees} placées,
        {execution.lignes_a_revoir} à revoir, {execution.lignes_echec} en échec.</p>}
    </section>
  </main>
}
