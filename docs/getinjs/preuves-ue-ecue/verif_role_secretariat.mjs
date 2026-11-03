/**
 * Vérification ciblée : l'écran UE/ECUE doit être utilisable par un compte
 * SECRETARIAT (autorisé à écrire les UE/ECUE) et pas seulement par un admin.
 *
 * Contrôle ce qu'un rôle ne peut pas deviner depuis les tests unitaires :
 * que la liste des maquettes se charge réellement pour lui, que les boutons
 * d'écriture sont là, et qu'une création aboutit vraiment en base.
 *
 * Compte de service à créer au préalable (le mot de passe n'est pas versionné
 * dans le dépôt ; recréer ce compte uniquement dans la base de développement) :
 *
 *   python manage.py shell -c "
 *   from authentication.models import User
 *   u,_ = User.objects.get_or_create(username='verif_secretariat',
 *                                     defaults={'role':'SECRETARIAT'})
 *   u.set_password('verif12345'); u.is_active=True; u.save()"
 */
import puppeteer from 'puppeteer-core';
import chromium from '@sparticuz/chromium';

const OUT = '/home/user/backend-injs2026/docs/getinjs/preuves-ue-ecue';
const SITE = 'http://127.0.0.1:3000';
const API = 'http://127.0.0.1:8000/api';
const pause = (ms) => new Promise((r) => setTimeout(r, ms));
const journal = [];
const verifier = (nom, ok, detail = '') => {
  journal.push({ nom, ok: Boolean(ok), detail });
  console.log(`${ok ? 'OK  ' : 'FAIL'} ${nom}${detail ? ' — ' + detail : ''}`);
  if (!ok) process.exitCode = 1;
};

const browser = await puppeteer.launch({
  executablePath: await chromium.executablePath(),
  headless: 'shell',
  args: [...chromium.args, '--no-sandbox', '--disable-dev-shm-usage', '--lang=fr-FR'],
  defaultViewport: { width: 1440, height: 950 },
});
const page = await browser.newPage();

await page.goto(`${SITE}/login`, { waitUntil: 'networkidle2' });
await page.waitForSelector('#login-username');
await page.type('#login-username', 'verif_secretariat');
await page.type('#login-password', 'verif12345');
await Promise.all([
  page.click('button.btn-login'),
  page.waitForFunction(() => !location.pathname.startsWith('/login'), { timeout: 30000 }),
]);
await pause(1500);

await page.goto(`${SITE}/referentiels/ue-ecue`, { waitUntil: 'networkidle2' });
await page.waitForSelector('[data-testid="choix-maquette"]', { timeout: 30000 });
await pause(2000);

const options = await page.$$eval('[data-testid="choix-maquette"] option', (os) => os
  .map((o) => o.value).filter(Boolean));
verifier('les maquettes sont listées pour un secrétariat', options.length > 0,
  `${options.length} maquettes proposées`);
verifier('aucun message de refus affiché', !(await page.$('[data-testid="erreur-maquettes"]')));
verifier('bouton « Nouvelle UE » disponible', Boolean(await page.$('[data-testid="nouvelle-ue"]')));

const token = await page.evaluate(() => localStorage.getItem('access_token'));
const entetes = token ? { Authorization: `Bearer ${token}` } : {};
const maquetteId = await page.$eval('[data-testid="choix-maquette"]', (s) => s.value);

// Création réelle depuis un compte secrétariat, puis suppression.
await page.click('[data-testid="nouvelle-ue"]');
await page.waitForSelector('[data-testid="formulaire-element"]', { timeout: 15000 });
await pause(400);
await page.type('[data-testid="element-code"]', 'SEC-UE01');
await page.type('[data-testid="element-intitule"]', 'UE créée par un secrétariat');
await page.type('[data-testid="element-credits"]', '2');
await page.screenshot({ path: `${OUT}/18-role-secretariat-formulaire.jpg`, type: 'jpeg', quality: 82 });
await page.click('[data-testid="element-enregistrer"]');
await pause(2200);

const ues = await (await fetch(`${API}/scolarite/maquettes/${maquetteId}/ues/`, { headers: entetes })).json();
const creee = ues.find((u) => u.code === 'SEC-UE01');
verifier('création effective depuis un compte secrétariat', Boolean(creee),
  creee ? `id=${creee.id} statut=${creee.statut}` : 'absente');
await page.screenshot({ path: `${OUT}/18-role-secretariat.jpg`, type: 'jpeg', quality: 82 });

if (creee) {
  const res = await fetch(`${API}/scolarite/ues/${creee.id}/`, { method: 'DELETE', headers: entetes });
  verifier('nettoyage de la ligne de test', res.status === 204, `HTTP ${res.status}`);
}

console.log(JSON.stringify(journal, null, 2));
await browser.close();
