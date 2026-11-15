import { downloadFile } from './downloadFile'

const escapeHtml = value => String(value).replace(/[&<>"']/g, char => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
})[char])
const csvCell = value => `"${String(value).replaceAll('"', '""')}"`

export function scolariteExportRows(titre, stats) {
  const general = [
    ['Étudiants inscrits', stats.etudiantsInscrits],
    ['Professeurs et encadreurs', stats.professeurs],
    ["Présents aujourd'hui", stats.presentsAujourdhui],
    ['Taux de présence', `${stats.tauxPresence}%`],
  ]
  const niveaux = ['L1', 'L2', 'L3', 'M1', 'M2'].map(n => [n, stats.niveaux[n] ?? 0])
  const finances = [['Frais payés', stats.fraisPayes], ['Frais en attente', stats.fraisEnAttente]]
  if (titre === 'Repartition_Niveaux') return niveaux
  if (titre === 'Finances_Etudiants') return finances
  return [...general, ...niveaux, ...finances]
}

/** Chaque format produit un vrai fichier, sans boîte de dialogue d'impression. */
export async function exporterScolarite(format, titre, stats, annee) {
  const rows = scolariteExportRows(titre, stats)
  const heading = `INJS UFR STAPS-JL — ${titre.replaceAll('_', ' ')}`
  const file = `INJS_Scolarite_${titre}`
  const date = new Date().toLocaleDateString('fr-FR')
  if (format === 'PDF') {
    const { jsPDF } = await import('jspdf')
    const pdf = new jsPDF()
    pdf.setFontSize(16)
    // Les polices PDF de base ne contiennent pas toutes les glyphes Unicode.
    pdf.text(heading.replace('—', '-'), 14, 20)
    pdf.setFontSize(10)
    pdf.text(`Annee academique : ${annee} | Date : ${date}`, 14, 30)
    rows.forEach(([label, value], i) => {
      const y = 45 + i * 11
      pdf.text(String(label).normalize('NFD').replace(/[\u0300-\u036f]/g, ''), 14, y)
      pdf.text(String(value), 150, y)
      pdf.setDrawColor(226, 232, 240)
      pdf.line(14, y + 3, 196, y + 3)
    })
    downloadFile(pdf.output('blob'), `${file}.pdf`)
  } else if (format === 'Excel') {
    const csv = '\ufeff' + [
      [heading, ''], ['Année académique', annee], ['Date', date],
      ['Indicateur', 'Valeur'], ...rows,
    ].map(row => row.map(csvCell).join(';')).join('\r\n')
    downloadFile(new Blob([csv], { type: 'text/csv;charset=utf-8' }), `${file}.csv`)
  } else if (format === 'Word') {
    const table = rows.map(([label, value]) => `<tr><td>${escapeHtml(label)}</td><td>${escapeHtml(value)}</td></tr>`).join('')
    const html = `<html><head><meta charset="utf-8"></head><body style="font-family:Arial,sans-serif"><h1>${escapeHtml(heading)}</h1><p>Année académique : ${escapeHtml(annee)} — ${escapeHtml(date)}</p><table border="1" cellspacing="0" cellpadding="8"><tr><th>Indicateur</th><th>Valeur</th></tr>${table}</table></body></html>`
    downloadFile(new Blob(['\ufeff', html], { type: 'application/msword' }), `${file}.doc`)
  } else {
    throw new Error(`Format inconnu : ${format}`)
  }
}
