/* Vérification postcss + couverture des classes premium (outil de contrôle). */
const fs = require('fs')
const path = require('path')
const postcss = require('postcss')

const root = path.resolve(__dirname, '..')
const files = [
  'src/styles/premiumCommun.css',
  'src/styles/formateurs.css',
  'src/styles/chargesEnseignants.css',
]

async function main() {
  for (const f of files) {
    const css = fs.readFileSync(path.join(root, f), 'utf8')
    await postcss.parse(css, { from: f })
    console.log('PARSE OK', f, css.split('\n').length, 'lignes')
  }

  const jsx = ['src/pages/Formateurs.jsx', 'src/pages/scolarite/ChargesEnseignants.jsx']
    .map((f) => fs.readFileSync(path.join(root, f), 'utf8'))
    .join('\n')
  const cssAll = files.map((f) => fs.readFileSync(path.join(root, f), 'utf8')).join('\n')

  const used = new Set()
  for (const m of jsx.matchAll(/(?:px-|ens-|chg-)[a-z0-9-]+/g)) used.add(m[0])
  const defined = new Set()
  for (const m of cssAll.matchAll(/\.((?:px-|ens-|chg-)[a-z0-9-]+)/g)) defined.add(m[1])

  const missing = [...used].filter((c) => !defined.has(c))
  console.log(
    'classes utilisées:', used.size,
    '| définies:', defined.size,
    '| manquantes:', missing.length ? missing.join(', ') : 'aucune',
  )
  if (missing.length) process.exit(1)
}

main().catch((e) => {
  console.error('ERREUR', e.message)
  process.exit(1)
})
