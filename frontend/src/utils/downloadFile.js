// Ne pas libérer l'object URL pendant que le navigateur initialise le téléchargement.
// Un lien attaché au document est nécessaire dans certains navigateurs (Safari notamment).
export function downloadFile(blob, fileName) {
  if (!(blob instanceof Blob) || blob.size === 0) {
    throw new Error('Le serveur a renvoyé un fichier vide.')
  }
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = fileName
  document.body.appendChild(link)
  try {
    link.click()
  } finally {
    link.remove()
    window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
  }
}
