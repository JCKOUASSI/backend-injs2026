import React, { useEffect, useState } from 'react'

/**
 * Aperçu du document exporté, affiché **dans la page**.
 *
 * Certains environnements — notamment les aperçus intégrés — interdisent à la
 * fois les téléchargements (`sandbox` sans `allow-downloads`) et l'ouverture
 * de fenêtres (`sandbox` sans `allow-popups`). Aucune remise de fichier n'y
 * est possible, quel que soit le code : le seul moyen de montrer le document
 * est de l'afficher, ce qui ne dépend d'aucune de ces deux autorisations.
 *
 * Deux cas sont couverts :
 * * les formats **texte** (CSV…), lus et affichés, avec un bouton de copie —
 *   le presse-papiers fonctionne sur un geste de l'utilisateur ;
 * * le **PDF**, rendu par la visionneuse intégrée du navigateur.
 *
 * Les formats binaires non affichables (Excel, Word) sont annoncés comme tels
 * plutôt que de laisser croire à un échec de l'export : le document est bien
 * produit, c'est son affichage qui est impossible ici.
 */

/** Extensions et types MIME affichables comme texte. */
const EST_TEXTE = (nom, contentType) =>
  /\.csv$/i.test(nom || '') ||
  /\.txt$/i.test(nom || '') ||
  /^(text\/|application\/json)/i.test(contentType || '')

const EST_PDF = (nom, contentType) =>
  /\.pdf$/i.test(nom || '') || /application\/pdf/i.test(contentType || '')

/** Nombre de caractères affichés : au-delà, l'aperçu perd son intérêt. */
const LIMITE_APERCU = 20_000

/**
 * Lit un blob comme texte.
 *
 * `Blob.prototype.text()` n'existe pas partout (anciens Safari, Firefox, et
 * l'environnement de test) : on retombe alors sur `FileReader`, qui fait la
 * même chose et ne dépend d'aucune version récente.
 */
function lireTexte(blob) {
  if (typeof blob.text === 'function') return blob.text()
  return new Promise((resoudre, refuser) => {
    const lecteur = new FileReader()
    lecteur.onload = () => resoudre(String(lecteur.result ?? ''))
    lecteur.onerror = () => refuser(lecteur.error || new Error('Lecture impossible'))
    lecteur.readAsText(blob)
  })
}

export default function ApercuDocument({ nom, blob, contentType }) {
  const [texte, setTexte] = useState(null)
  const [urlAffichage, setUrlAffichage] = useState(null)
  const [copie, setCopie] = useState('')

  // Lecture du contenu texte : asynchrone, donc annulable si le composant
  // disparaît avant la fin (changement d'export, fermeture du panneau).
  useEffect(() => {
    let annule = false
    if (!blob || !(contentType || '').startsWith('application/pdf')) {
      if (blob && EST_TEXTE(nom, contentType)) {
        lireTexte(blob).then((contenu) => {
          if (!annule) setTexte(contenu)
        }).catch(() => { if (!annule) setTexte(null) })
      } else {
        setTexte(null)
      }
    }
    return () => { annule = true }
  }, [blob, contentType, nom])

  // URL d'affichage du PDF : une URL d'objet ne porte **aucun**
  // `Content-Disposition`, donc le navigateur affiche le document au lieu de
  // chercher à le télécharger. C'est ce qui rend l'aperçu possible là où une
  // URL serveur (qui, elle, impose `attachment`) échouerait.
  useEffect(() => {
    if (!blob || !EST_PDF(nom, contentType)) {
      setUrlAffichage(null)
      return undefined
    }
    const url = window.URL.createObjectURL(blob)
    setUrlAffichage(url)
    return () => window.URL.revokeObjectURL(url)
  }, [blob, contentType, nom])

  const copier = async () => {
    try {
      await navigator.clipboard.writeText(texte || '')
      setCopie('Copié')
    } catch {
      // Presse-papiers indisponible (permissions, contexte non sécurisé) :
      // le texte reste sélectionnable manuellement dans le bloc ci-dessous.
      setCopie('Copie impossible — sélectionnez le texte')
    }
    window.setTimeout(() => setCopie(''), 2500)
  }

  if (texte != null) {
    const tronque = texte.length > LIMITE_APERCU
    return (
      <div className="ref-apercu">
        <div className="ref-apercu-entete">
          <span>Contenu du fichier</span>
          <button type="button" className="ref-apercu-copier" onClick={copier}>
            <i className="bi bi-clipboard" aria-hidden="true" /> Copier
          </button>
          {copie && <span className="ref-apercu-copie" role="status">{copie}</span>}
        </div>
        <pre className="ref-apercu-texte">
          {tronque ? texte.slice(0, LIMITE_APERCU) : texte}
          {tronque && '\n… (aperçu tronqué — le fichier complet est généré côté serveur)'}
        </pre>
      </div>
    )
  }

  if (urlAffichage) {
    return (
      <div className="ref-apercu">
        <div className="ref-apercu-entete"><span>Aperçu du PDF</span></div>
        <iframe
          className="ref-apercu-pdf"
          src={urlAffichage}
          title={`Aperçu de ${nom}`}
        />
      </div>
    )
  }

  // Format binaire non affichable : le dire, sans laisser croire à un échec.
  return (
    <p className="ref-apercu-indisponible">
      Ce format ne peut pas être affiché ici, mais le fichier a bien été généré
      par le serveur. Ouvrez l’application hors de cet aperçu intégré pour le
      télécharger.
    </p>
  )
}
