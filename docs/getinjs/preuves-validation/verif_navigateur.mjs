/**
 * Validation navigateur — bundle de PRODUCTION (`vite preview`, port 3100).
 *
 * Trois volets, volontairement distingués dans le rapport :
 *   1. POSTE DE TRAVAIL (1440×900) — parcours critiques et erreurs API ;
 *   2. MATRICE RESPONSIVE (360 → 1440 px) — débordement horizontal réel,
 *      mesuré contre `documentElement.clientWidth` (et non `innerWidth`, qui
 *      grandit avec le contenu et masquerait justement le défaut) ;
 *   3. ÉMULATION MOBILE (390×844, 360×800) — parcours complet.
 *
 * Aucun appareil physique n'est utilisé : le volet 3 est de l'émulation de
 * viewport dans Chromium, pas un test sur téléphone réel.
 *
 * Prérequis : API sur :8000 et bundle servi par `npx vite preview --port 3100`.
 * Exécution  : LD_LIBRARY_PATH=/tmp/chlibs node verif_navigateur.mjs
 */
import puppeteer from 'puppeteer-core';
import chromium from '@sparticuz/chromium';
import fs from 'node:fs';

const OUT = '/home/user/backend-injs2026/docs/getinjs/preuves-validation';
fs.mkdirSync(OUT, { recursive: true });
const SITE = process.env.SITE || 'http://127.0.0.1:3100';
const pause = (ms) => new Promise((r) => setTimeout(r, ms));
const journal = [];
const verifier = (nom, ok, detail = '') => {
  journal.push({ nom, ok: Boolean(ok), detail });
  console.log(`${ok ? 'OK  ' : 'FAIL'} ${nom}${detail ? ' — ' + detail : ''}`);
  if (!ok) process.exitCode = 1;
};

const bruit = /WebSocket|vite|Download the React DevTools|Failed to load resource: the server responded with a status of 500/;

const browser = await puppeteer.launch({
  executablePath: await chromium.executablePath(),
  headless: 'shell',
  args: [...chromium.args, '--no-sandbox', '--disable-dev-shm-usage', '--lang=fr-FR'],
  defaultViewport: null,
});

async function nouvelOnglet(viewport) {
  const page = await browser.newPage();
  await page.setViewport(viewport);
  const erreurs = [];
  page.on('console', (m) => { if (m.type() === 'error') erreurs.push(m.text()); });
  page.on('pageerror', (e) => erreurs.push(`pageerror: ${e.message}`));
  page.erreurs = erreurs;
  return page;
}

async function connexion(page) {
  await page.goto(`${SITE}/login`, { waitUntil: 'networkidle2' });
  // Les onglets d'un même navigateur partagent localStorage : si la session
  // est déjà active, /login redirige et le formulaire n'existe pas.
  if (!page.url().includes('/login')) return;
  await page.waitForSelector('#login-username', { timeout: 30000 });
  await page.type('#login-username', 'admin');
  await page.type('#login-password', 'admin123');
  await Promise.all([
    page.click('button.btn-login'),
    page.waitForFunction(() => !location.pathname.startsWith('/login'), { timeout: 30000 }),
  ]);
  await pause(1200);
}

/**
 * Ouvre un écran en garantissant une session active. Si l'application a renvoyé
 * vers /login (jeton purgé entre deux navigations), on le CONSIGNE comme
 * incident — il ne doit pas passer inaperçu — puis on se reconnecte, plutôt que
 * de mesurer la page de connexion en croyant mesurer l'écran.
 */
const incidents = [];
async function ouvrirPage(page, chemin) {
  await page.goto(`${SITE}${chemin}`, { waitUntil: 'networkidle2' });
  await pause(600);
  if (page.url().includes('/login')) {
    incidents.push(`session perdue à l’ouverture de ${chemin} — reconnexion`);
    console.log(`!! session perdue à l’ouverture de ${chemin} — reconnexion`);
    await connexion(page);
    await page.goto(`${SITE}${chemin}`, { waitUntil: 'networkidle2' });
    await pause(600);
  }
  return page.url();
}

async function ouvrirEcran(page) {
  await page.goto(`${SITE}/referentiels/ue-ecue`, { waitUntil: 'networkidle2' });
  await page.waitForSelector('[data-testid="choix-maquette"]', { timeout: 30000 });
  await pause(1600);
}

/** Débordement horizontal mesuré sur la largeur de mise en page réelle. */
/**
 * Applique un viewport ET attend que la mise en page l'ait réellement pris en
 * compte : après un long enchaînement d'émulations, `window.innerWidth` peut
 * accuser un retard d'une frame, ce qui fausserait les mesures suivantes.
 */
async function viewport(page, largeur, hauteur, mobile = false) {
  await page.setViewport({
    width: largeur, height: hauteur, isMobile: mobile, hasTouch: mobile, deviceScaleFactor: 1,
  });
  // On attend sur `matchMedia` : `window.innerWidth` peut dépasser la largeur
  // demandée lorsque la page déborde (layout viewport élargi), ce qui rendrait
  // l'attente impossible même une fois le viewport correctement appliqué.
  await page.waitForFunction(
    (w) => window.matchMedia(`(width: ${w}px)`).matches, { timeout: 10000 }, largeur,
  );
}

async function debordement(page) {
  return page.evaluate(() => {
    const vw = document.documentElement.clientWidth;
    const coupe = (el) => {
      let e = el.parentElement;
      while (e) {
        const o = getComputedStyle(e).overflowX;
        if (o === 'hidden' || o === 'auto' || o === 'scroll') return true;
        e = e.parentElement;
      }
      return false;
    };
    const coupables = [];
    document.querySelectorAll('body *').forEach((el) => {
      const r = el.getBoundingClientRect();
      if (r.right > vw + 1 && r.width > 0 && r.height > 0 && !coupe(el)) {
        coupables.push(`${el.tagName.toLowerCase()}.${String(el.className).slice(0, 32)}`);
      }
    });
    return { vw, sw: document.documentElement.scrollWidth, coupables: coupables.slice(0, 3) };
  });
}

async function cliquer(page, selecteur) {
  const el = await page.waitForSelector(selecteur, { timeout: 15000 });
  await el.evaluate((n) => n.scrollIntoView({ block: 'center' }));
  await pause(150);
  await el.click();
}

// ═══════════════════════════════════════════════════════════════════════════
// 1. POSTE DE TRAVAIL
// ═══════════════════════════════════════════════════════════════════════════
const bureau = await nouvelOnglet({ width: 1440, height: 900 });
await connexion(bureau);
verifier('connexion sur le bundle de production', !bureau.url().includes('/login'), SITE);
await ouvrirEcran(bureau);

const nbUe = await bureau.$$eval('[data-testid^="ligne-ue-"]', (l) => l.length);
verifier('liste des UE rendue par le bundle minifié', nbUe > 0, `${nbUe} lignes`);
const nbEcue = await bureau.$$eval('[data-testid^="ligne-ecue-"]', (l) => l.length);
verifier('panneau ECUE alimenté', nbEcue > 0, `${nbEcue} lignes`);
await bureau.screenshot({ path: `${OUT}/01-production-desktop.jpg`, type: 'jpeg', quality: 82 });

const sansNom = await bureau.evaluate(() => [...document.querySelectorAll('button, a, input, select')]
  .filter((el) => {
    if (!(el.offsetParent !== null || el.getClientRects().length)) return false;
    const nom = el.getAttribute('aria-label') || el.getAttribute('title') || (el.innerText || '').trim()
      || (el.labels && el.labels.length ? el.labels[0].innerText : '') || el.getAttribute('placeholder') || '';
    return !nom;
  })
  .map((el) => `${el.tagName.toLowerCase()}:${(el.getAttribute('data-testid') || el.className || '').slice(0, 36)}`));
verifier('aucun contrôle interactif sans nom accessible', sansNom.length === 0, sansNom.slice(0, 4).join(', '));

await cliquer(bureau, '[data-testid="nouvelle-ue"]');
await bureau.waitForSelector('[data-testid="formulaire-element"]', { timeout: 15000 });
await pause(400);
const champsNommes = await bureau.evaluate(() => [...document.querySelectorAll(
  '[data-testid="formulaire-element"] input, [data-testid="formulaire-element"] select',
)].filter((el) => el.type !== 'hidden')
  .map((el) => Boolean((el.labels && el.labels.length) || el.getAttribute('aria-label'))));
verifier('tous les champs du formulaire ont un libellé associé',
  champsNommes.length > 0 && champsNommes.every(Boolean), `${champsNommes.length} champs`);
await bureau.screenshot({ path: `${OUT}/02-production-formulaire.jpg`, type: 'jpeg', quality: 82 });
await bureau.keyboard.press('Escape');
await pause(400);

// ── Erreur API à la création (interception : aucune écriture en base) ───────
await bureau.setRequestInterception(true);
const refusCreation = (req) => {
  const url = req.url();
  if (url.includes('/api/scolarite/maquettes/') && url.endsWith('/ues/') && req.method() === 'POST') {
    req.respond({
      status: 500, contentType: 'application/json',
      body: JSON.stringify({ error: 'Erreur interne simulée par le test de validation.' }),
    });
    return;
  }
  req.continue();
};
bureau.on('request', refusCreation);
await cliquer(bureau, '[data-testid="nouvelle-ue"]');
await bureau.waitForSelector('[data-testid="formulaire-element"]', { timeout: 15000 });
await pause(300);
await bureau.type('[data-testid="element-code"]', 'VAL-ERR01');
await bureau.type('[data-testid="element-intitule"]', 'Test erreur API');
await bureau.click('[data-testid="element-enregistrer"]');
await pause(1800);
const messageErreur = await bureau.$eval('[data-testid="element-erreur"]', (e) => e.textContent.trim()).catch(() => null);
verifier('une erreur API 500 est expliquée à l’utilisateur', Boolean(messageErreur), messageErreur || 'aucun message');
verifier('le formulaire reste ouvert (saisie non perdue)',
  Boolean(await bureau.$('[data-testid="formulaire-element"]')));
await bureau.screenshot({ path: `${OUT}/03-production-erreur-api.jpg`, type: 'jpeg', quality: 82 });
await bureau.keyboard.press('Escape');
await pause(300);
bureau.off('request', refusCreation);

// ── Erreur API à la lecture des maquettes ──────────────────────────────────
const refusLecture = (req) => {
  if (req.url().endsWith('/api/scolarite/maquettes/')) {
    req.respond({ status: 500, contentType: 'application/json', body: '{"error":"panne simulée"}' });
    return;
  }
  req.continue();
};
bureau.on('request', refusLecture);
await bureau.goto(`${SITE}/referentiels/ue-ecue`, { waitUntil: 'networkidle2' });
await pause(2500);
const bandeau = await bureau.$('[data-testid="erreur-maquettes"]');
verifier('un échec de chargement affiche un message, pas une page vide', Boolean(bandeau),
  bandeau ? (await bureau.$eval('[data-testid="erreur-maquettes"]', (e) => e.textContent.trim())).slice(0, 80) : 'absent');
await bureau.screenshot({ path: `${OUT}/04-production-echec-lecture.jpg`, type: 'jpeg', quality: 82 });
bureau.off('request', refusLecture);
await bureau.setRequestInterception(false);

const erreursBureau = bureau.erreurs.filter((e) => !bruit.test(e));
verifier('aucune erreur JavaScript inattendue (poste de travail)', erreursBureau.length === 0,
  erreursBureau.slice(0, 2).join(' | '));
await bureau.close();

// ═══════════════════════════════════════════════════════════════════════════
// 2. MATRICE RESPONSIVE
// ═══════════════════════════════════════════════════════════════════════════
const pageResponsive = await nouvelOnglet({ width: 1440, height: 900 });
await connexion(pageResponsive);
for (const chemin of ['/referentiels/ue-ecue', '/referentiels/niveaux', '/']) {
  for (const largeur of [360, 390, 768, 1024, 1440]) {
    await viewport(pageResponsive, largeur, 800, largeur < 768);
    await ouvrirPage(pageResponsive, chemin);
    await pause(1200);
    const m = await debordement(pageResponsive);
    verifier(`pas de débordement horizontal — ${chemin} @ ${largeur}px`,
      m.sw <= m.vw + 1 && !pageResponsive.url().includes('/login'),
      `scrollWidth ${m.sw} / mise en page ${m.vw}${m.coupables.length ? ' — ' + m.coupables.join(',') : ''}`);
  }
}
await viewport(pageResponsive, 1440, 900);
await ouvrirPage(pageResponsive, '/referentiels/ue-ecue');
await pause(1500);
const utilitaires = await pageResponsive.evaluate(() => {
  const nav = document.querySelector('nav.d-none.d-xl-block');
  const pillule = [...document.querySelectorAll('div')]
    .find((d) => (d.getAttribute('title') || '').startsWith('Année Acad'));
  const visible = (el) => Boolean(el) && getComputedStyle(el).display !== 'none';
  return {
    filAriane: visible(nav), pillule: visible(pillule),
    detail: {
      iw: window.innerWidth, mq1200: matchMedia('(min-width:1200px)').matches,
      topBar: Boolean(document.querySelector('.top-bar')), navPresente: Boolean(nav), pilulePresente: Boolean(pillule),
      url: location.pathname,
    },
  };
});
verifier('bureau : fil d’Ariane visible (≥1200 px)', utilitaires.filAriane, JSON.stringify(utilitaires.detail));
verifier('bureau : pilule d’année visible (≥768 px)', utilitaires.pillule);

await viewport(pageResponsive, 390, 844, true);
await ouvrirPage(pageResponsive, '/referentiels/ue-ecue');
await pause(1500);
const mobiles = await pageResponsive.evaluate(() => {
  const nav = document.querySelector('nav.d-none.d-xl-block');
  const pillule = [...document.querySelectorAll('div')]
    .find((d) => (d.getAttribute('title') || '').startsWith('Année Acad'));
  const visible = (el) => Boolean(el) && getComputedStyle(el).display !== 'none';
  return { filAriane: visible(nav), pillule: visible(pillule) };
});
verifier('mobile : pilule d’année masquée (<768 px)', !mobiles.pillule);
verifier('mobile : fil d’Ariane masqué (<1200 px)', !mobiles.filAriane);
await pageResponsive.close();

// ═══════════════════════════════════════════════════════════════════════════
// 3. ÉMULATION MOBILE
// ═══════════════════════════════════════════════════════════════════════════
const APPAREILS = [
  { nom: 'iPhone 12', viewport: { width: 390, height: 844, isMobile: true, hasTouch: true, deviceScaleFactor: 3 },
    ua: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1' },
  { nom: 'Android 360×800', viewport: { width: 360, height: 800, isMobile: true, hasTouch: true, deviceScaleFactor: 2 },
    ua: 'Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Mobile Safari/537.36' },
];

for (const [index, appareil] of APPAREILS.entries()) {
  const page = await nouvelOnglet(appareil.viewport);
  await page.setUserAgent(appareil.ua);
  // Session vierge : le jeton du poste de travail ferait rediriger /login.
  await page.goto(SITE, { waitUntil: 'domcontentloaded' });
  await page.evaluate(() => window.localStorage.clear());
  await connexion(page);
  verifier(`[${appareil.nom}] connexion réussie`, !page.url().includes('/login'));
  await ouvrirEcran(page);

  const d = await debordement(page);
  verifier(`[${appareil.nom}] aucun débordement horizontal`, d.sw <= d.vw + 1,
    `scrollWidth ${d.sw} / mise en page ${d.vw}`);

  const panneaux = await page.evaluate(() => [...document.querySelectorAll('.ue-ecue-panneau')]
    .map((el) => { const r = el.getBoundingClientRect(); return { top: Math.round(r.top), bottom: Math.round(r.bottom) }; }));
  verifier(`[${appareil.nom}] panneaux empilés verticalement`,
    panneaux.length === 2 && panneaux[1].top >= panneaux[0].bottom - 5,
    panneaux.map((p) => `${p.top}→${p.bottom}`).join(' | '));

  const lignes = await page.$$eval('[data-testid^="ligne-ue-"]', (l) => l.length);
  verifier(`[${appareil.nom}] les UE restent listées`, lignes > 0, `${lignes} lignes`);
  await page.screenshot({ path: `${OUT}/0${5 + index}-mobile-${appareil.viewport.width}.jpg`, type: 'jpeg', quality: 82 });

  await cliquer(page, '[data-testid="nouvelle-ue"]');
  await page.waitForSelector('[data-testid="formulaire-element"]', { timeout: 15000 });
  await pause(500);
  const modale = await page.evaluate(() => {
    const r = document.querySelector('[role="dialog"]').getBoundingClientRect();
    return { left: Math.round(r.left), right: Math.round(r.right), vw: window.innerWidth };
  });
  verifier(`[${appareil.nom}] formulaire contenu dans la largeur`,
    modale.left >= 0 && modale.right <= modale.vw + 1, `gauche ${modale.left}, droite ${modale.right}, viewport ${modale.vw}`);
  await page.screenshot({ path: `${OUT}/0${7 + index}-mobile-formulaire-${appareil.viewport.width}.jpg`, type: 'jpeg', quality: 82 });
  await page.keyboard.press('Escape');

  const erreursMobile = page.erreurs.filter((e) => !bruit.test(e));
  verifier(`[${appareil.nom}] aucune erreur JavaScript`, erreursMobile.length === 0, erreursMobile.slice(0, 2).join(' | '));
  await page.close();
}

fs.writeFileSync(`${OUT}/journal-navigateur.json`, JSON.stringify({
  execute_le: new Date().toISOString(),
  site: SITE,
  bundle: 'production (vite preview)',
  moteur: 'Chromium headless (@sparticuz/chromium)',
  mobile: 'émulation de viewport — aucun appareil physique',
  incidents_session: incidents,
  verification: journal,
}, null, 2));

await browser.close();
const echecs = journal.filter((v) => !v.ok).length;
console.log(`\n${journal.length - echecs}/${journal.length} vérifications OK`);
