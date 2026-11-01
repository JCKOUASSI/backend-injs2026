/* Recette de bout en bout du module Référentiels (mission 53).
 *
 * Ce script n'observe pas seulement : il **agit** dans l'interface réelle —
 * création, modification, archivage, réactivation — et vérifie chaque effet
 * à l'écran, plus le corps des réponses de l'API.
 *
 * Il est rejouable : le code de la valeur de recette est horodaté
 * (`RECETTE53_HHMMSS`), la comparaison des libellés se fait donc toujours sur
 * une ligne neuve. La commande d'import des référentiels produisant des codes
 * stables, aucun code de recette ne peut entrer en collision avec une donnée
 * réelle ; en cas de collision, la création échoue et le script s'arrête.
 *
 * Usage :
 *   node scripts/recette-referentiels.cjs
 *   BASE=http://127.0.0.1:3100 SORTIE=/chemin/captures node scripts/recette-referentiels.cjs
 */
const fs = require('fs')
const path = require('path')
const puppeteer = require('puppeteer-core')
const chromiumModule = require('@sparticuz/chromium')
const chromium = chromiumModule.default || chromiumModule

const BASE = process.env.BASE || 'http://127.0.0.1:3100'
const SORTIE = process.env.SORTIE || '/home/user/backend-injs2026/docs/audits/53/captures/recette'
const HORODATAGE = new Date().toISOString().slice(11, 19).replace(/:/g, '')
const CODE = process.env.CODE || `RECETTE53_${HORODATAGE}`
// Le libellé est horodaté comme le code : l'anti-doublon du module refuse — à
// raison — deux valeurs de même libellé, et une recette doit rester rejouable.
const LIBELLE = `Recette de bout en bout ${HORODATAGE}`
const LIBELLE_MODIFIE = `${LIBELLE} (modifiée)`

const pause = (ms) => new Promise((r) => setTimeout(r, ms))

/** Une ligne du tableau contient-elle `code` (et, si fourni, `texte`) ? */
const jsLigne = (code, present, texte = null) => `[...document.querySelectorAll('.ref-table tbody tr')]
  .some((tr) => tr.innerText.includes(${JSON.stringify(code)})
    && ${texte === null ? 'true' : `tr.innerText.includes(${JSON.stringify(texte)})`}) === ${present}`

async function main() {
  fs.mkdirSync(SORTIE, { recursive: true })
  const navigateur = await puppeteer.launch({
    args: [...chromium.args, '--no-sandbox', '--disable-dev-shm-usage'],
    defaultViewport: { width: 1440, height: 960, deviceScaleFactor: 1 },
    executablePath: await chromium.executablePath(),
    headless: 'shell',
  })
  const page = await navigateur.newPage()
  const erreurs = []
  const appels = []
  const reponsesEcriture = []
  page.on('console', (m) => { if (m.type() === 'error') erreurs.push(m.text()) })
  page.on('pageerror', (e) => erreurs.push(`pageerror: ${e.message}`))
  page.on('response', async (r) => {
    const url = r.url()
    if (!url.includes('/api/referentiels/')) return
    const ligne = `${r.request().method()} ${url.split('/api')[1]} → ${r.status()}`
    appels.push(ligne)
    if (r.request().method() !== 'GET') {
      let corps = null
      try { corps = await r.json() } catch { corps = '<non JSON>' }
      reponsesEcriture.push({ ligne, corps })
      console.log(`  ↳ ${ligne} ${JSON.stringify(corps)}`)
      if (r.status() >= 400) erreurs.push(`API ${ligne} ${JSON.stringify(corps)}`)
    }
  })

  // 1. Connexion réelle (mêmes identifiants que l'aperçu admin)
  await page.goto(`${BASE}/login`, { waitUntil: 'networkidle2' })
  const jeton = await page.evaluate(async () => {
    const r = await fetch('/api/auth/login/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: 'admin', password: 'admin123' }),
    })
    if (!r.ok) throw new Error(`login ${r.status}`)
    return r.json()
  })
  await page.evaluate((d) => {
    localStorage.setItem('access_token', d.access)
    localStorage.setItem('user', JSON.stringify(d.user || {}))
  }, jeton)
  console.log(`connecté : ${jeton.user?.username} ${jeton.user?.role} — code de recette ${CODE}`)

  // 2. Création
  await page.goto(`${BASE}/referentiels/gestion/types-evaluation`, { waitUntil: 'networkidle2' })
  await page.waitForSelector('.cand-btn-principal')
  await page.click('.cand-btn-principal')
  await page.waitForSelector('.ref-modale')
  await page.type('#ref-code', CODE)
  await page.type('#ref-libelle', LIBELLE)
  await page.select('#ref-fiabilite', 'OFFICIEL')
  await page.type('#ref-source', 'Recette automatisée mission 53')
  await page.click('.ref-modale button[type=submit]')
  // La modale ne se referme qu'en cas de succès : un refus (ex. code déjà pris)
  // laisse le formulaire ouvert avec son message d'erreur.
  await page.waitForFunction(() => !document.querySelector('.ref-modale'), { timeout: 10000 })
  await page.waitForFunction(jsLigne(CODE, true), { timeout: 10000 }, CODE)
  await pause(400)
  await page.screenshot({ path: path.join(SORTIE, '09-recette-creation.png') })
  console.log(`création : ligne « ${CODE} » visible dans le tableau`)

  // 3. Modification du libellé
  const ligne = await page.evaluateHandle(
    (code) => [...document.querySelectorAll('.ref-table tbody tr')].find((tr) => tr.innerText.includes(code)),
    CODE,
  )
  const crayon = await ligne.asElement().$('.ref-action')
  await crayon.click()
  await page.waitForSelector('.ref-modale')
  await page.click('#ref-libelle', { clickCount: 3 })
  await page.type('#ref-libelle', LIBELLE_MODIFIE)
  await page.click('.ref-modale button[type=submit]')
  // La modale se referme sur succès ; la ligne de recette porte le nouveau
  // libellé (une autre ligne pourrait porter le même texte, on cible la nôtre).
  await page.waitForFunction(() => !document.querySelector('.ref-modale'), { timeout: 10000 })
  await page.waitForFunction(jsLigne(CODE, true, '(modifiée)'), { timeout: 10000 }, CODE)
  await pause(400)
  await page.screenshot({ path: path.join(SORTIE, '10-recette-modification.png') })
  console.log('modification : libellé mis à jour à l’écran')

  // 4. Archivage, avec confirmation explicite
  const ligne2 = await page.evaluateHandle(
    (code) => [...document.querySelectorAll('.ref-table tbody tr')].find((tr) => tr.innerText.includes(code)),
    CODE,
  )
  const archiver = await ligne2.asElement().$('.ref-action--archiver')
  await archiver.click()
  await page.waitForSelector('.ref-modale--etroite')
  await pause(250)
  await page.click('.ref-btn-danger')
  await page.waitForFunction(jsLigne(CODE, false), { timeout: 10000 }, CODE)
  // 4 bis. La valeur reste consultable dans le filtre « Archivés »
  await page.waitForSelector('#ref-filtre-etat', { timeout: 10000 })
  await page.select('#ref-filtre-etat', 'archives')
  await page.waitForFunction(jsLigne(CODE, true), { timeout: 10000 }, CODE)
  await pause(400)
  await page.screenshot({ path: path.join(SORTIE, '11-recette-archivee.png') })
  console.log('archivage : ligne masquée des actifs, présente dans « Archivés »')

  // 5. Réactivation : la valeur doit redevenir utilisable, pas seulement
  //    sortir de l'archive (sinon elle reste absente du filtre « Actifs »).
  const ligne3 = await page.evaluateHandle(
    (code) => [...document.querySelectorAll('.ref-table tbody tr')].find((tr) => tr.innerText.includes(code)),
    CODE,
  )
  const reactiver = await ligne3.asElement().$('.ref-action--reactiver')
  await reactiver.click()
  await pause(900)
  await page.waitForSelector('#ref-filtre-etat', { timeout: 10000 })
  await page.select('#ref-filtre-etat', 'actifs')
  await page.waitForFunction(jsLigne(CODE, true), { timeout: 10000 }, CODE)
  const corpsReactivation = reponsesEcriture
    .filter((r) => r.ligne.includes('/reactiver/')).pop()
  if (corpsReactivation && corpsReactivation.corps?.actif !== true) {
    throw new Error(`réactivation : la valeur n’est pas redevenue active (${JSON.stringify(corpsReactivation.corps)})`)
  }
  console.log('réactivation : ligne de nouveau active et visible dans « Actifs »')

  // 6. Contrôle du journal (traçabilité des quatre opérations)
  const journal = await page.evaluate(async (code) => {
    const r = await fetch('/api/referentiels/journal/?page_size=200', {
      headers: { Authorization: `Bearer ${localStorage.getItem('access_token')}` },
    })
    if (!r.ok) return { erreur: r.status }
    const d = await r.json()
    return { total: d.count, actions: d.results.map((j) => j.action) }
  }, CODE)
  if (journal.erreur) throw new Error(`journal illisible : ${journal.erreur}`)
  console.log(`journal : ${journal.total} entrée(s) — actions présentes :`, journal.actions.slice(0, 6).join(', '))

  // 7. Référentiel non éditable : aucune action d'écriture proposée
  await page.goto(`${BASE}/referentiels/gestion/modules-officiels`, { waitUntil: 'networkidle2' })
  await page.waitForSelector('.ref-table--lecture')
  const boutons = await page.$$eval('.ref-table--lecture .ref-action', (b) => b.length)
  const boutonAjouter = await page.$('.cand-btn-principal')
  console.log(`lecture seule : ${boutons} action(s) dans le tableau, bouton Ajouter ${boutonAjouter ? 'PRÉSENT' : 'absent'}`)
  if (boutons > 0 || boutonAjouter) throw new Error('lecture seule : des actions d’écriture sont proposées')

  console.log('\nappels API observés :')
  appels.forEach((a) => console.log('  ' + a))
  console.log(`\nrelevés d’écriture : ${reponsesEcriture.length}`)
  console.log('erreurs console :', erreurs.length ? erreurs : 'aucune')
  await navigateur.close()
  if (erreurs.length) process.exit(1)
}

main().catch((e) => {
  console.error('ÉCHEC :', e.message)
  process.exit(1)
})
