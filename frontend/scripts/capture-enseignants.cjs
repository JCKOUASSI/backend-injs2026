/* Captures d'écran du contrôle « Enseignants » + assiduité mesurée.
 * Chromium fourni par @sparticuz/chromium (aucun root requis).
 *
 *   BASE=http://127.0.0.1:3000 SORTIE=... node frontend/scripts/capture-enseignants.cjs
 */
const fs = require('fs')
const path = require('path')
const puppeteer = require('puppeteer-core')
const chromiumModule = require('@sparticuz/chromium')
const chromium = chromiumModule.default || chromiumModule

const BASE = process.env.BASE || 'http://127.0.0.1:3000'
const SORTIE = process.env.SORTIE || '/home/user/backend-injs2026/arena/previews/controle-35'
const USER = process.env.USER_INJS || 'admin'
const PASS = process.env.PASS_INJS || 'admin123'
const LARGEUR = Number(process.env.LARGEUR || 1600)
const HAUTEUR = Number(process.env.HAUTEUR || 1000)

const attendre = (ms) => new Promise((r) => setTimeout(r, ms))

async function main() {
  fs.mkdirSync(SORTIE, { recursive: true })
  const navigateur = await puppeteer.launch({
    args: [...chromium.args, '--no-sandbox', '--disable-dev-shm-usage'],
    defaultViewport: { width: LARGEUR, height: HAUTEUR, deviceScaleFactor: 1 },
    executablePath: await chromium.executablePath(),
    headless: 'shell',
  })
  const page = await navigateur.newPage()
  const erreurs = []
  page.on('console', (m) => { if (m.type() === 'error') erreurs.push(m.text()) })
  page.on('pageerror', (e) => erreurs.push(`pageerror: ${e.message}`))

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

  const capture = async (nom, chemin, { pleinPage = false, avant } = {}) => {
    await page.goto(`${BASE}${chemin}`, { waitUntil: 'networkidle2' })
    await attendre(1500)
    if (avant) await avant()
    await page.screenshot({ path: path.join(SORTIE, `${nom}.png`), fullPage: pleinPage })
    console.log('capture', nom)
  }

  const ouvrirFiche = async () => {
    const boutons = await page.$$('button')
    for (const b of boutons) {
      const texte = await page.evaluate((el) => el.textContent || '', b)
      if (texte.includes('Détail')) { await b.click(); break }
    }
    await page.waitForSelector('.ens-fiche-modal', { timeout: 15000 })
    await attendre(1200)
  }

  await capture('apres-formateurs', '/formateurs', { pleinPage: false })
  await capture('apres-formateurs-fiche', '/formateurs', { avant: ouvrirFiche })
  // Onglet « Charge annuelle » de la fiche
  await page.evaluate(() => {
    const onglet = [...document.querySelectorAll('.ens-fiche-modal .px-tab')]
      .find((b) => b.textContent.includes('Charge annuelle'))
    onglet?.click()
  })
  await attendre(900)
  await page.screenshot({ path: path.join(SORTIE, 'apres-formateurs-fiche-charge.png') })
  console.log('capture apres-formateurs-fiche-charge')

  await capture('apres-charges', '/scolarite/charges')
  await capture('apres-dashboard', '/dashboard')

  console.log('erreurs console :', erreurs.length ? erreurs : 'aucune')
  await navigateur.close()
}

main().catch((e) => { console.error('ÉCHEC :', e); process.exit(1) })
