/* Capture d'écran des écrans du module Référentiels (mission 53).
 * Chromium fourni par @sparticuz/chromium (aucun root requis).
 */
const fs = require('fs')
const path = require('path')
const puppeteer = require('puppeteer-core')
const chromiumModule = require('@sparticuz/chromium')
const chromium = chromiumModule.default || chromiumModule

const BASE = process.env.BASE || 'http://127.0.0.1:3100'
const SORTIE = process.env.SORTIE || '/home/user/backend-injs2026/docs/audits/53/captures'
const USER = process.env.USER_INJS || 'admin'
const PASS = process.env.PASS_INJS || 'admin123'

const ECHELLE = Number(process.env.ECHELLE || 1)
const LARGEUR = Number(process.env.LARGEUR || 1440)
const HAUTEUR = Number(process.env.HAUTEUR || 960)

async function main() {
  fs.mkdirSync(SORTIE, { recursive: true })
  const navigateur = await puppeteer.launch({
    args: [...chromium.args, '--no-sandbox', '--disable-dev-shm-usage'],
    defaultViewport: { width: LARGEUR, height: HAUTEUR, deviceScaleFactor: ECHELLE },
    executablePath: await chromium.executablePath(),
    headless: 'shell',
  })
  const page = await navigateur.newPage()
  const erreurs = []
  page.on('console', (m) => {
    if (m.type() === 'error') erreurs.push(m.text())
  })
  page.on('pageerror', (e) => erreurs.push(`pageerror: ${e.message}`))

  // Connexion réelle via l'API puis injection du jeton (même mécanisme que l'app).
  await page.goto(`${BASE}/login`, { waitUntil: 'networkidle2' })
  const jeton = await page.evaluate(async ({ u, p }) => {
    const reponse = await fetch('/api/auth/login/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: u, password: p }),
    })
    if (!reponse.ok) throw new Error(`login ${reponse.status}`)
    return reponse.json()
  }, { u: USER, p: PASS })
  await page.evaluate((d) => {
    localStorage.setItem('access_token', d.access)
    localStorage.setItem('refresh_token', d.refresh || '')
    localStorage.setItem('user', JSON.stringify(d.user || {}))
  }, jeton)
  console.log('connecté :', jeton.user?.username, jeton.user?.role)

  // `pleinPage` est désactivé sur les longues listes (227 modules, 51 volumes) :
  // une capture pleine page y produirait une bande illisible.
  const captures = [
    ['01-tableau-de-bord', '/referentiels', true],
    ['02-filieres', '/referentiels/gestion/filieres', true],
    ['03-modules-officiels', '/referentiels/gestion/modules-officiels', false],
    ['04-volumes-horaires', '/referentiels/gestion/volumes-modules', false],
    ['05-ecoles', '/referentiels/gestion/ecoles', true],
    ['06-type-evaluation', '/referentiels/gestion/types-evaluation', true],
  ]
  for (const [nom, chemin, pleinPage] of captures) {
    await page.goto(`${BASE}${chemin}`, { waitUntil: 'networkidle2' })
    await page.waitForSelector('.ref-page, .cand-page', { timeout: 15000 })
    await new Promise((r) => setTimeout(r, 900))
    await page.screenshot({ path: path.join(SORTIE, `${nom}.png`), fullPage: pleinPage })
    console.log('capture', nom)
  }

  // Formulaire de création : sélecteurs dépendants (filière → école, mention)
  await page.goto(`${BASE}/referentiels/gestion/filieres`, { waitUntil: 'networkidle2' })
  await page.waitForSelector('.cand-btn-principal')
  await page.click('.cand-btn-principal')
  await page.waitForSelector('.ref-modale')
  await page.select('#ref-ecole', await page.$eval('#ref-ecole option:nth-child(2)', (o) => o.value))
  await new Promise((r) => setTimeout(r, 500))
  const optionsMentions = await page.$$eval('#ref-mention option', (os) => os.map((o) => o.textContent))
  console.log('mentions proposées après choix de l’école :', optionsMentions)
  await page.screenshot({ path: path.join(SORTIE, '07-formulaire-filiere.png') })

  // Confirmation d'archivage
  await page.keyboard.press('Escape')
  await page.evaluate(() => document.querySelector('.ref-modale-fermer')?.click())
  await new Promise((r) => setTimeout(r, 400))
  const aArchiver = await page.$('.ref-action--archiver')
  if (aArchiver) {
    await aArchiver.click()
    await page.waitForSelector('.ref-modale--etroite')
    await new Promise((r) => setTimeout(r, 300))
    await page.screenshot({ path: path.join(SORTIE, '08-confirmation-archivage.png') })
    await page.evaluate(() => {
      const boutons = [...document.querySelectorAll('.ref-modale--etroite button')]
      boutons.find((b) => b.classList.contains('cand-btn-fantome'))?.click()
    })
  }

  console.log('erreurs console :', erreurs.length ? erreurs : 'aucune')
  await navigateur.close()
}

main().catch((e) => {
  console.error('ÉCHEC :', e)
  process.exit(1)
})
