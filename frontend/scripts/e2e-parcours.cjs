/* Parcours E2E réel — connexion + visite des modules principaux.
 *
 * Ce script agit dans l'interface réelle (Chromium headless) et relève, pour
 * chaque écran : les erreurs JavaScript, les requêtes API en échec (>= 400) et
 * les pages qui n'affichent pas de contenu.
 *
 * Usage :
 *   BASE=http://127.0.0.1:3000 node scripts/e2e-parcours.cjs
 *   BASE=... UTILISATEUR=admin MOT_DE_PASSE=... node scripts/e2e-parcours.cjs
 */
const fs = require('fs')
const puppeteer = require('puppeteer-core')
const chromiumModule = require('@sparticuz/chromium')
const chromium = chromiumModule.default || chromiumModule

const BASE = process.env.BASE || 'http://127.0.0.1:3000'
const UTILISATEUR = process.env.UTILISATEUR || 'admin'
const MOT_DE_PASSE = process.env.MOT_DE_PASSE || 'AdminDemo2026'
const SORTIE = process.env.SORTIE || '/tmp/e2e-injs'

const ECRANS = [
  '/dashboard',
  '/scolarite',
  '/scolarite/maquettes',
  '/scolarite/inscriptions',
  '/scolarite/etudiants',
  '/scolarite/finances',
  '/formations-etudes',
  '/formations',
  '/participants',
  '/formateurs',
  '/modules',
  '/edts',
  '/edt/new',
  '/presences',
  '/evaluations',
  '/notes',
  '/jurys',
  '/deliberations',
  '/diplomes',
  '/statistiques',
  '/referentiels',
  '/administration/comptes',
  '/parametres',
]

const pause = (ms) => new Promise((r) => setTimeout(r, ms))

async function main() {
  fs.mkdirSync(SORTIE, { recursive: true })
  const navigateur = await puppeteer.launch({
    args: [...chromium.args, '--no-sandbox', '--disable-dev-shm-usage'],
    defaultViewport: { width: 1440, height: 960 },
    executablePath: await chromium.executablePath(),
    headless: 'shell',
  })

  const page = await navigateur.newPage()
  const incidents = []
  let ecranCourant = 'connexion'

  page.on('pageerror', (e) => incidents.push({ ecran: ecranCourant, type: 'js', message: e.message }))
  page.on('console', (m) => {
    if (m.type() === 'error') incidents.push({ ecran: ecranCourant, type: 'console', message: m.text() })
  })
  page.on('response', async (r) => {
    const url = r.url()
    if (!url.includes('/api/') || url.includes('/auth/capabilities')) return
    if (r.status() >= 400) {
      incidents.push({ ecran: ecranCourant, type: 'api', statut: r.status(), url })
    }
    if (r.status() >= 500) {
      incidents.push({ ecran: ecranCourant, type: 'api-500', statut: r.status(), url })
    }
  })

  // 1. Connexion
  await page.goto(`${BASE}/login`, { waitUntil: 'networkidle2' })
  await page.type('input[name="username"], #username, input[type="text"]', UTILISATEUR)
  await page.type('input[type="password"]', MOT_DE_PASSE)
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'networkidle2', timeout: 30000 }).catch(() => {}),
    page.click('button[type="submit"]'),
  ])
  await pause(1500)
  const urlApresLogin = page.url()
  console.log(`connexion → ${urlApresLogin}`)

  // 2. Écrans
  const resultats = []
  for (const chemin of ECRANS) {
    ecranCourant = chemin
    const avant = incidents.length
    try {
      await page.goto(`${BASE}${chemin}`, { waitUntil: 'networkidle2', timeout: 30000 })
    } catch (e) {
      incidents.push({ ecran: chemin, type: 'navigation', message: e.message })
    }
    await pause(900)
    const mesure = await page.evaluate(() => {
      const racine = document.querySelector('main') || document.body
      return {
        url: location.pathname,
        texte: (racine.innerText || '').trim().length,
        titre: (document.querySelector('h1, .page-title, .titre-page')?.innerText || '').trim(),
        erreursVisibles: [...document.querySelectorAll('.alert-danger, .toast-error, [role="alert"]')]
          .map((n) => n.innerText.trim()).filter(Boolean).slice(0, 3),
        titreDocument: document.title,
      }
    })
    const nouveaux = incidents.slice(avant)
    resultats.push({ chemin, ...mesure, incidents: nouveaux })
    await page.screenshot({ path: `${SORTIE}/${chemin.replace(/\//g, '_') || 'racine'}.png` })
    const etat = mesure.erreursVisibles.length || nouveaux.length ? 'ATTENTION' : 'OK'
    console.log(
      `${etat.padEnd(9)} ${chemin.padEnd(28)} url=${mesure.url.padEnd(28)} `
      + `texte=${String(mesure.texte).padStart(5)} incidents=${nouveaux.length}`,
    )
  }

  fs.writeFileSync(`${SORTIE}/rapport.json`, JSON.stringify({ urlApresLogin, resultats, incidents }, null, 2))

  const bloquants = incidents.filter((i) => i.type === 'api-500' || i.type === 'js')
  console.log('---------------------------------------------')
  console.log(`écrans visités : ${ECRANS.length}`)
  console.log(`incidents : ${incidents.length} (dont ${bloquants.length} bloquants)`)
  for (const i of incidents.slice(0, 40)) {
    console.log(`  [${i.ecran}] ${i.type} ${i.statut || ''} ${i.url || i.message || ''}`)
  }
  await navigateur.close()
  if (bloquants.length) process.exitCode = 1
}

main().catch((e) => {
  console.error('ÉCHEC DU PARCOURS :', e)
  process.exit(2)
})
