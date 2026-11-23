/**
 * PerimetresOrganisation — sélecteurs de bornage Direction / Département.
 *
 * LOT 5 (écart L4-02) : la console ne se limite plus au périmètre
 * secrétariat ; la ligne d'attribution peut porter des périmètres de tout
 * type posables ({type, object_id}). Ce bloc ajoute les deux familles
 * organisationnelles (les types pédagogiques restent posables par l'API,
 * l'admin Django demeurant le repli universel). Additif et optionnel :
 * sans données, le composant ne rend rien.
 */
import { useEffect, useState } from 'react'
import { listerDepartements, listerDirections } from '@/services/habilitations'

export function basculerBorne(perimetres, type, ids) {
  const gardes = perimetres.filter((p) => p.type !== type)
  return [...gardes, ...ids.map((object_id) => ({ type, object_id }))]
}

export default function PerimetresOrganisation({
  directions: directionsProp, departements: departementsProp,
  perimetres = [], onChange,
}) {
  const [directionsInternes, setDirectionsInternes] = useState([])
  const [departementsInternes, setDepartementsInternes] = useState([])
  const directions = directionsProp ?? directionsInternes
  const departements = departementsProp ?? departementsInternes

  useEffect(() => {
    if (directionsProp === undefined) {
      listerDirections().then(setDirectionsInternes).catch(() => setDirectionsInternes([]))
    }
    if (departementsProp === undefined) {
      listerDepartements().then(setDepartementsInternes).catch(() => setDepartementsInternes([]))
    }
  }, [directionsProp, departementsProp])

  if (!directions.length && !departements.length) return null

  const selectionnes = (type) => perimetres
    .filter((p) => p.type === type)
    .map((p) => String(p.object_id))

  const onChangeType = (type) => (e) => {
    const ids = Array.from(e.target.selectedOptions, (o) => Number(o.value))
    onChange?.(basculerBorne(perimetres, type, ids))
  }

  return (
    <div className="mt-2" data-testid="bornage-organisation">
      {directions.length > 0 && (
        <div className="mb-2">
          <label className="form-label">Directions couvertes (facultatif)</label>
          <select multiple className="form-select" style={{ minHeight: 80 }}
                  data-testid="select-directions"
                  value={selectionnes('DIRECTION')}
                  onChange={onChangeType('DIRECTION')}>
            {directions.map((d) => (
              <option key={d.id} value={d.id}>{d.libelle} ({d.code})</option>
            ))}
          </select>
        </div>
      )}
      {departements.length > 0 && (
        <div>
          <label className="form-label">Départements couverts (facultatif)</label>
          <select multiple className="form-select" style={{ minHeight: 80 }}
                  data-testid="select-departements"
                  value={selectionnes('DEPARTEMENT')}
                  onChange={onChangeType('DEPARTEMENT')}>
            {departements.map((d) => (
              <option key={d.id} value={d.id}>{d.libelle} ({d.code})</option>
            ))}
          </select>
        </div>
      )}
    </div>
  )
}
