/** JournalHabilitations — consultation filtrable et vérification du chaînage. */
import { useCallback, useEffect, useState } from 'react'
import { listerJournal, integriteJournal, messageErreur } from '@/services/habilitations'
import { telechargerCsv } from '@/utils/habilitations'
import { EnChargement } from './partages'
import './habilitations.css'

const TYPES = [
  'COMPTE_CREE', 'COMPTE_ACTIVE', 'COMPTE_SUSPENDU', 'COMPTE_DESACTIVE',
  'COMPTE_VERROUILLE', 'ROLE_ATTRIBUE', 'ROLE_REVOQUE',
  'PERMISSION_OCTROYEE', 'PERMISSION_RETIREE',
  'DELEGATION_CREE', 'DELEGATION_REVOQUEE', 'CONNEXION', 'CONNEXION_ECHOUEE',
]

export default function JournalHabilitations() {
  const [donnees, setDonnees] = useState(null)
  const [chargement, setChargement] = useState(true)
  const [erreurChargement, setErreurChargement] = useState('')
  const [integrite, setIntegrite] = useState(null)
  const [erreurIntegrite, setErreurIntegrite] = useState('')
  const [filtres, setFiltres] = useState({ type: '', q: '', date_min: '', date_max: '' })
  const [page, setPage] = useState(1)

  const chargerJournal = useCallback(async () => {
    setChargement(true)
    setErreurChargement('')
    const params = Object.fromEntries(Object.entries(filtres).filter(([, v]) => v))
    try {
      setDonnees(await listerJournal({ ...params, page }))
    } catch (e) {
      setErreurChargement(messageErreur(e, 'Chargement du journal impossible.'))
    } finally {
      setChargement(false)
    }
  }, [filtres, page])

  const chargerIntegrite = useCallback(async () => {
    setErreurIntegrite('')
    try {
      setIntegrite(await integriteJournal())
    } catch (e) {
      setErreurIntegrite(messageErreur(e, 'Vérification de l’intégrité du journal impossible.'))
    }
  }, [])

  useEffect(() => { chargerJournal() }, [chargerJournal])
  useEffect(() => { chargerIntegrite() }, [chargerIntegrite])

  const maj = (k, v) => { setPage(1); setFiltres((f) => ({ ...f, [k]: v })) }
  const totalPages = donnees ? Math.max(1, Math.ceil(donnees.count / 50)) : 1
  const exporterCsv = () => {
    telechargerCsv(
      'journal_habilitations.csv',
      ['numero', 'horodatage', 'evenement', 'acteur', 'objet', 'motif'],
      donnees.results.map((e) => [
        e.numero, e.horodatage, e.type_libelle, e.acteur, e.objet_libelle, e.motif,
      ]),
    )
  }

  return (
    <section data-testid="ecran-journal">
      <div className="hab-carte">
        <div className="d-flex justify-content-between align-items-center">
          <h2 className="h5 mb-0">Journal des habilitations</h2>
          <button type="button" className="btn btn-outline-success btn-sm" data-testid="export-journal"
                  onClick={exporterCsv} disabled={!donnees || donnees.results.length === 0}>
            <i className="bi bi-download me-1" />Exporter (CSV)
          </button>
        </div>
        {integrite && (
          <div className={integrite.integre ? 'hab-avertissement' : 'hab-avertissement bloquant'}
               style={{ borderLeftColor: integrite.integre ? '#1d6b35' : '#c62828', background: integrite.integre ? '#e8f5ec' : '#fbe7e7' }}
               data-testid="integrite-journal">
            <i className={`bi ${integrite.integre ? 'bi-patch-check' : 'bi-x-octagon'} me-1`} />
            {integrite.integre
              ? `Chaînage intègre — ${integrite.total} événement(s) vérifié(s).`
              : `ANOMALIE détectée : ${integrite.anomalies.join(', ')}`}
          </div>
        )}
        {erreurIntegrite && (
          <div className="hab-avertissement" role="alert" data-testid="integrite-journal-erreur">
            <p>{erreurIntegrite}</p>
            <button type="button" className="btn btn-sm btn-outline-primary" onClick={chargerIntegrite}>Réessayer la vérification</button>
          </div>
        )}
        <div className="hab-filtres">
          <select className="form-select" value={filtres.type} aria-label="Type d'événement"
                  onChange={(e) => maj('type', e.target.value)}>
            <option value="">Tous les événements</option>
            {TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
          <input className="form-control" placeholder="Motif, acteur, objet…" value={filtres.q}
                 onChange={(e) => maj('q', e.target.value)} data-testid="filtre-journal" />
          <input type="date" className="form-control" aria-label="Du" value={filtres.date_min}
                 onChange={(e) => maj('date_min', e.target.value)} />
          <input type="date" className="form-control" aria-label="Au" value={filtres.date_max}
                 onChange={(e) => maj('date_max', e.target.value)} />
        </div>
      </div>
      <div className="hab-carte">
        {chargement ? <EnChargement message="Chargement du journal…" /> : erreurChargement ? (
          <div className="hab-avertissement" role="alert" data-testid="journal-erreur">
            <p>{erreurChargement}</p>
            <button type="button" className="btn btn-sm btn-outline-primary" onClick={chargerJournal}>Réessayer</button>
          </div>
        ) : donnees && (
          <table className="hab-table">
            <thead><tr><th>N°</th><th>Horodatage</th><th>Événement</th><th>Acteur</th><th>Objet</th><th>Motif</th></tr></thead>
            <tbody>
              {donnees.results.map((e) => (
                <tr key={e.numero} data-testid="ligne-journal">
                  <td>{e.numero}</td>
                  <td className="hab-muted">{e.horodatage.slice(0, 16).replace('T', ' ')}</td>
                  <td>{e.type_libelle}</td>
                  <td>{e.acteur}</td>
                  <td className="hab-muted">{e.objet_libelle}</td>
                  <td>{e.motif}</td>
                </tr>
              ))}
              {donnees.results.length === 0 && <tr><td colSpan="6" className="hab-muted text-center py-3">Aucun événement.</td></tr>}
            </tbody>
          </table>
        )}
        {totalPages > 1 && (
          <div className="d-flex justify-content-between mt-2">
            <button className="btn btn-sm btn-secondary" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Précédent</button>
            <span className="hab-muted">Page {page}/{totalPages}</span>
            <button className="btn btn-sm btn-secondary" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>Suivant</button>
          </div>
        )}
      </div>
    </section>
  )
}
