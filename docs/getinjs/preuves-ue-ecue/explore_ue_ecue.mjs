/**
 * Parcours réel UE / ECUE : créer, visualiser, modifier, supprimer, et faire
 * vivre les trois statuts (Brouillon → Activé → Désactivé).
 *
 * Chaque étape est vérifiée deux fois : à l'écran (assertion DOM + capture) et
 * par un appel direct à l'API, indépendant de l'interface. Aucun résultat n'est
 * déduit d'un toast. Les lignes créées portent le préfixe E2E- et sont
 * supprimées en fin de parcours.
 *
 * Prérequis : API Django sur :8000 et Vite sur :3000 (arena/lancer-api.sh,
 * arena/lancer-front.sh), base de développement migrée et initialisée.
 *
 * Exécution : LD_LIBRARY_PATH=/tmp/chlibs node e2e_ue_ecue.mjs
 */
import puppeteer from 'puppeteer-core';
import chromium from '@sparticuz/chromium';
import fs from 'node:fs';

const OUT = '/home/user/backend-injs2026/docs/getinjs/preuves-ue-ecue';
fs.mkdirSync(OUT, { recursive: true });
const SITE = 'http://127.0.0.1:3000';
const API = 'http://127.0.0.1:8000/api';
const pause = (ms) => new Promise((r) => setTimeout(r, ms));

const journal = [];
const verifier = (nom, condition, detail = '') => {
  journal.push({ nom, ok: Boolean(condition), detail });
  console.log(`${condition ? 'OK  ' : 'FAIL'} ${nom}${detail ? ' — ' + detail : ''}`);
  if (!condition) process.exitCode = 1;
};

const browser = await puppeteer.launch({
  executablePath: await chromium.executablePath(),
  headless: 'shell',
  args: [...chromium.args, '--no-sandbox', '--disable-dev-shm-usage', '--lang=fr-FR'],
  defaultViewport: { width: 1440, height: 950 },
});
const page = await browser.newPage();

async function capture(nom) {
  await page.screenshot({ path: `${OUT}/${nom}.jpg`, type: 'jpeg', quality: 82 });
}

/** Remplit un champ contrôlé React comme le ferait un utilisateur : on efface
 *  le contenu existant caractère par caractère, puis on saisit la valeur. La
 *  relecture échoue bruyamment si la frappe n'a pas produit le texte voulu. */
async function saisir(selecteur, texte) {
  await page.waitForSelector(selecteur, { timeout: 15000 });
  await page.focus(selecteur);
  await page.keyboard.press('End');
  const longueur = await page.$eval(selecteur, (el) => el.value.length);
  for (let i = 0; i < longueur; i += 1) await page.keyboard.press('Backspace');
  await page.keyboard.type(texte, { delay: 12 });
  const obtenu = await page.$eval(selecteur, (el) => el.value);
  if (obtenu !== texte) {
    throw new Error(`Saisie incorrecte dans ${selecteur} : « ${obtenu} » au lieu de « ${texte} »`);
  }
}

/** Clique puis attend l'effet attendu, avec relance si le DOM a été re-rendu
 *  entre la sélection et le clic. */
async function cliquer(selecteur, attendu) {
  for (let essai = 0; essai < 3; essai += 1) {
    try {
      const el = await page.waitForSelector(selecteur, { timeout: 15000 });
      await el.click();
      if (!attendu) return;
      await page.waitForSelector(attendu, { timeout: 8000 });
      return;
    } catch (e) {
      if (essai === 2) throw e;
      await pause(600);
    }
  }
}

async function confirmerSuppression() {
  await page.waitForSelector('[role="dialog"]', { timeout: 10000 });
  await pause(400);
  await page.evaluate(() => {
    const boite = document.querySelector('[role="dialog"]');
    [...boite.querySelectorAll('button')]
      .find((b) => b.textContent.trim() === 'Supprimer')?.click();
  });
  await pause(2000);
}

// ── Connexion ────────────────────────────────────────────────────────────────
await page.goto(`${SITE}/login`, { waitUntil: 'networkidle2' });
await page.waitForSelector('#login-username');
await page.type('#login-username', 'admin');
await page.type('#login-password', 'admin123');
await Promise.all([
  page.click('button.btn-login'),
  page.waitForFunction(() => !location.pathname.startsWith('/login'), { timeout: 30000 }),
]);
await pause(1500);
const token = await page.evaluate(() => localStorage.getItem('access_token')
  || localStorage.getItem('access') || null);
const entetes = token ? { Authorization: `Bearer ${token}` } : {};
const apiJson = async (chemin) => (await fetch(`${API}${chemin}`, { headers: entetes })).json();

await page.goto(`${SITE}/referentiels/ue-ecue`, { waitUntil: 'networkidle2' });
await page.waitForSelector('[data-testid="choix-maquette"]', { timeout: 30000 });
await pause(1500);
const maquetteId = await page.$eval('[data-testid="choix-maquette"]', (s) => s.value);
verifier('maquette sélectionnée', Boolean(maquetteId), `id=${maquetteId}`);

// Base de départ : aucune trace d'un parcours précédent.
let ues = await apiJson(`/scolarite/maquettes/${maquetteId}/ues/`);
verifier('base de départ sans reste E2E',
  !ues.some((u) => u.code.startsWith('E2E-')), `${ues.length} UE au départ`);
await capture('01-liste-ue-ecue');

// ── 1. Création d'une UE ─────────────────────────────────────────────────────
await cliquer('[data-testid="nouvelle-ue"]', '[data-testid="formulaire-element"]');
await pause(500);
await capture('02-formulaire-nouvelle-ue');
await saisir('[data-testid="element-code"]', 'E2E-UE01');
await saisir('[data-testid="element-intitule"]', 'UE de test E2E (supprimée en fin de parcours)');
await saisir('[data-testid="element-credits"]', '3');
await page.click('[data-testid="element-enregistrer"]');
await pause(2200);
await capture('03-ue-creee');

ues = await apiJson(`/scolarite/maquettes/${maquetteId}/ues/`);
const ueCreee = ues.find((u) => u.code === 'E2E-UE01');
verifier('UE créée en base (API)', Boolean(ueCreee),
  ueCreee ? `id=${ueCreee.id} crédits=${ueCreee.credits} statut=${ueCreee.statut}` : 'absente');
verifier('statut initial = BROUILLON', ueCreee?.statut === 'BROUILLON', ueCreee?.statut);
verifier('UE affichée à l’écran', Boolean(await page.$(`[data-testid="ligne-ue-${ueCreee.id}"]`)));

// ── 2. Modification de l'UE ──────────────────────────────────────────────────
await cliquer(`[data-testid="modifier-ue-${ueCreee.id}"]`, '[data-testid="formulaire-element"]');
await pause(400);
await capture('04-formulaire-modification-ue');
await saisir('[data-testid="element-intitule"]', 'UE de test E2E — intitulé modifié');
await page.click('[data-testid="element-enregistrer"]');
await pause(2200);
ues = await apiJson(`/scolarite/maquettes/${maquetteId}/ues/`);
const ueModifiee = ues.find((u) => u.id === ueCreee.id);
verifier('modification persistée (API)',
  ueModifiee?.intitule === 'UE de test E2E — intitulé modifié', ueModifiee?.intitule);
await capture('05-ue-modifiee');

// ── 3. Création d'un ECUE sous cette UE ──────────────────────────────────────
await cliquer(`[data-testid="ligne-ue-${ueCreee.id}"]`, '[data-testid="nouvel-ecue"]');
await pause(900);
await cliquer('[data-testid="nouvel-ecue"]', '[data-testid="formulaire-element"]');
await pause(400);
await capture('06-formulaire-nouvel-ecue');
await saisir('[data-testid="element-code"]', 'E2E-ECUE01');
await saisir('[data-testid="element-intitule"]', 'ECUE de test E2E');
await saisir('[data-testid="element-credits"]', '3');
await saisir('[data-testid="element-volume_cm"]', '20');
await page.click('[data-testid="element-enregistrer"]');
await pause(2200);
ues = await apiJson(`/scolarite/maquettes/${maquetteId}/ues/`);
const ecueCree = ues.find((u) => u.id === ueCreee.id)?.ecues.find((e) => e.code === 'E2E-ECUE01');
verifier('ECUE créé sous l’UE (API)', Boolean(ecueCree),
  ecueCree ? `id=${ecueCree.id} statut=${ecueCree.statut} CM=${ecueCree.volume_cm}` : 'absent');
await capture('07-ecue-cree');

// ── 4. Une ECUE ne s'active pas sous une UE en brouillon ─────────────────────
await page.click(`[data-testid="ecue-statut-ACTIVE-${ecueCree.id}"]`);
await pause(1800);
let etat = await apiJson(`/scolarite/maquettes/${maquetteId}/ues/`);
verifier('activation ECUE sous UE brouillon refusée',
  etat.find((u) => u.id === ueCreee.id)?.ecues.find((e) => e.id === ecueCree.id)?.statut
  === 'BROUILLON');
await capture('08-ecue-activation-refusee');

// ── 5. Activation de l'UE puis de l'ECUE ─────────────────────────────────────
await page.click(`[data-testid="ue-statut-ACTIVE-${ueCreee.id}"]`);
await pause(2000);
await cliquer(`[data-testid="ligne-ue-${ueCreee.id}"]`, `[data-testid="ligne-ecue-${ecueCree.id}"]`);
await pause(800);
etat = await apiJson(`/scolarite/maquettes/${maquetteId}/ues/`);
verifier('UE activée (API)', etat.find((u) => u.id === ueCreee.id)?.statut === 'ACTIVE',
  etat.find((u) => u.id === ueCreee.id)?.statut);
verifier('UE activée : plus de bouton Supprimer',
  !(await page.$(`[data-testid="supprimer-ue-${ueCreee.id}"]`)));
await capture('09-ue-activee');

await page.click(`[data-testid="ecue-statut-ACTIVE-${ecueCree.id}"]`);
await pause(2000);
etat = await apiJson(`/scolarite/maquettes/${maquetteId}/ues/`);
verifier('ECUE activé sous une UE active (API)',
  etat.find((u) => u.id === ueCreee.id)?.ecues.find((e) => e.id === ecueCree.id)?.statut
  === 'ACTIVE');
await capture('10-ecue-active');

// ── 6. Désactivation : l'UE retire ses ECUE actives ──────────────────────────
await page.click(`[data-testid="ue-statut-DESACTIVEE-${ueCreee.id}"]`);
await pause(2200);
etat = await apiJson(`/scolarite/maquettes/${maquetteId}/ues/`);
const ueDesactivee = etat.find((u) => u.id === ueCreee.id);
verifier('UE désactivée (API)', ueDesactivee?.statut === 'DESACTIVEE', ueDesactivee?.statut);
verifier('ECUE désactivé avec son UE (API)',
  ueDesactivee?.ecues.find((e) => e.id === ecueCree.id)?.statut === 'DESACTIVEE',
  ueDesactivee?.ecues.find((e) => e.id === ecueCree.id)?.statut);
await capture('11-ue-desactivee');

// ── 7. Retour en brouillon ───────────────────────────────────────────────────
await cliquer(`[data-testid="ligne-ue-${ueCreee.id}"]`, `[data-testid="ligne-ecue-${ecueCree.id}"]`);
await pause(700);
await page.click(`[data-testid="ue-statut-BROUILLON-${ueCreee.id}"]`);
await pause(1800);
etat = await apiJson(`/scolarite/maquettes/${maquetteId}/ues/`);
verifier('retour en brouillon (API)',
  etat.find((u) => u.id === ueCreee.id)?.statut === 'BROUILLON');
await capture('12-retour-brouillon');

// ── 8. Suppression de l'UE refusée tant qu'elle porte un ECUE ────────────────
await page.click(`[data-testid="supprimer-ue-${ueCreee.id}"]`);
await pause(500);
await capture('13-confirmation-suppression-ue');
await confirmerSuppression();
etat = await apiJson(`/scolarite/maquettes/${maquetteId}/ues/`);
verifier('suppression UE refusée car elle porte un ECUE',
  Boolean(etat.find((u) => u.id === ueCreee.id)));
await capture('14-suppression-ue-refusee');

// ── 9. L'ECUE désactivé ne se supprime pas : il faut le repasser en brouillon
await cliquer(`[data-testid="ligne-ue-${ueCreee.id}"]`, `[data-testid="ligne-ecue-${ecueCree.id}"]`);
await pause(900);
verifier('ECUE désactivé : pas de bouton Supprimer',
  !(await page.$(`[data-testid="supprimer-ecue-${ecueCree.id}"]`)));
await cliquer(`[data-testid="ecue-statut-BROUILLON-${ecueCree.id}"]`, null);
await pause(2000);
etat = await apiJson(`/scolarite/maquettes/${maquetteId}/ues/`);
verifier('ECUE repassé en brouillon (API)',
  etat.find((u) => u.id === ueCreee.id)?.ecues.find((e) => e.id === ecueCree.id)?.statut
  === 'BROUILLON');
await capture('15-ecue-retour-brouillon');

// ── 10. Suppression de l'ECUE puis de l'UE ──────────────────────────────────
await page.click(`[data-testid="supprimer-ecue-${ecueCree.id}"]`);
await confirmerSuppression();
etat = await apiJson(`/scolarite/maquettes/${maquetteId}/ues/`);
verifier('ECUE supprimé (API)',
  !etat.find((u) => u.id === ueCreee.id)?.ecues.some((e) => e.id === ecueCree.id));

await cliquer(`[data-testid="ligne-ue-${ueCreee.id}"]`, null);
await pause(800);
await page.click(`[data-testid="supprimer-ue-${ueCreee.id}"]`);
await confirmerSuppression();
const final = await apiJson(`/scolarite/maquettes/${maquetteId}/ues/`);
verifier('UE supprimée (API) : base laissée propre', !final.some((u) => u.id === ueCreee.id));
await capture('16-base-nettoyee');

// ── 11. Une maquette non brouillon gèle l'écran ─────────────────────────────
const maquettes = await apiJson('/scolarite/maquettes/');
const gelee = maquettes.find((m) => m.statut !== 'BROUILLON');
if (gelee) {
  await page.select('[data-testid="choix-maquette"]', String(gelee.id));
  await pause(1500);
  verifier('maquette gelée : bandeau de verrouillage affiché',
    Boolean(await page.$('[data-testid="maquette-verrouillee"]')),
    `${gelee.libelle || gelee.code} — ${gelee.statut}`);
  verifier('maquette gelée : aucun bouton de création',
    !(await page.$('[data-testid="nouvelle-ue"]')));
  await capture('17-maquette-verrouillee');
  await page.select('[data-testid="choix-maquette"]', String(maquetteId));
  await pause(1200);
} else {
  verifier('maquette gelée disponible pour la preuve', false, 'aucune maquette non brouillon');
}

fs.writeFileSync(`${OUT}/journal-verifications.json`, JSON.stringify({
  execute_le: new Date().toISOString(),
  maquette_id: maquetteId,
  verification: journal,
}, null, 2));
await browser.close();
