import React from 'react'
import BarreExport from './BarreExport'

/**
 * Barre d'actions d'un référentiel : **Importer** puis **Exporter**.
 *
 * Les deux actions sont volontairement réunies dans un seul bloc et
 * partagent le même langage visuel : l'utilisateur comprend d'un coup d'œil
 * qu'elles portent sur le même périmètre (celui affiché à l'écran).
 *
 * L'import n'est proposé que si le référentiel est éditable : un
 * référentiel en lecture seule n'expose ni import ni export d'écriture, ce
 * qui est une restriction métier — jamais une limitation de lecture.
 */
export default function BarreImportExport({
  slug,
  filtres = {},
  total = 0,
  onImporter,
  onMessage,
  lectureSeule = false,
}) {
  return (
    <div className="ref-actions">
      {!lectureSeule && (
        <button
          type="button"
          className="ref-btn ref-btn--import"
          onClick={onImporter}
          title="Importer un fichier Excel ou CSV"
        >
          <span className="ref-btn-icone" aria-hidden="true">
            <i className="bi bi-upload" />
          </span>
          <span>Importer</span>
        </button>
      )}

      <BarreExport slug={slug} filtres={filtres} total={total} onMessage={onMessage} />

      {lectureSeule && (
        <span className="ref-actions-note">
          <i className="bi bi-shield-lock" aria-hidden="true" /> Référentiel consultable et
          exportable, non modifiable.
        </span>
      )}
    </div>
  )
}
