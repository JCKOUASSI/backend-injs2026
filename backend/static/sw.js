const CACHE_NAME = 'qr-badge-v3';

const CDN_ASSETS = [
    'https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css',
    'https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css',
    'https://unpkg.com/html5-qrcode@2.3.8/html5-qrcode.min.js',
];

// ── Install: pre-cache CDN assets ──
self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => cache.addAll(CDN_ASSETS))
    );
    self.skipWaiting();
});

// ── Activate: clean old caches ──
self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((keys) =>
            Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
        )
    );
    self.clients.claim();
});

// ── Fetch: intercept requests ──
self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);

    // Never intercept POST requests
    if (event.request.method !== 'GET') return;

    // ── Badge page: network-first, cache fallback (ignore query params) ──
    if (url.pathname === '/dashboard/badge/') {
        event.respondWith(
            fetch(event.request)
                .then((response) => {
                    // Cache a clean copy (without query params) for offline use
                    const cacheKey = new Request(url.origin + '/dashboard/badge/');
                    const clone = response.clone();
                    caches.open(CACHE_NAME).then((cache) => cache.put(cacheKey, clone));
                    return response;
                })
                .catch(async () => {
                    // Offline: serve cached version of badge page
                    const cacheKey = new Request(url.origin + '/dashboard/badge/');
                    const cached = await caches.match(cacheKey);
                    if (cached) return cached;
                    // Ultimate fallback: generate a minimal offline badge page
                    return new Response(OFFLINE_BADGE_HTML, {
                        headers: { 'Content-Type': 'text/html; charset=utf-8' },
                    });
                })
        );
        return;
    }

    // ── Offline-data API: stale-while-revalidate ──
    // Données quasi-statiques (~450 KB). On sert immédiatement la copie en
    // cache si elle existe et on rafraîchit en arrière-plan : la majorité des
    // requêtes ne touchent plus le backend (réduit fortement la charge CPU).
    if (url.pathname.includes('/offline-data/') || url.pathname.includes('/scan/offline-data')) {
        event.respondWith(
            caches.match(event.request).then((cached) => {
                const networkFetch = fetch(event.request)
                    .then((response) => {
                        // Ne cacher que les réponses valides (200)
                        if (response && response.ok) {
                            const clone = response.clone();
                            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
                        }
                        return response;
                    })
                    .catch(() => cached);
                // Cache hit → réponse instantanée + revalidation en arrière-plan
                return cached || networkFetch;
            })
        );
        return;
    }

    // ── Static assets & CDN: cache-first, network fallback ──
    if (url.pathname.startsWith('/static/') || url.hostname !== location.hostname) {
        event.respondWith(
            caches.match(event.request).then((cached) => {
                if (cached) {
                    // Stale-while-revalidate
                    fetch(event.request).then((response) => {
                        caches.open(CACHE_NAME).then((cache) => cache.put(event.request, response));
                    }).catch(() => {});
                    return cached;
                }
                return fetch(event.request).then((response) => {
                    const clone = response.clone();
                    caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
                    return response;
                });
            })
        );
        return;
    }
});

// ── Background sync: replay offline scans when online ──
self.addEventListener('sync', (event) => {
    if (event.tag === 'sync-scans') {
        event.waitUntil(replayOfflineScans());
    }
});

async function replayOfflineScans() {
    const db = await openDB();
    const tx = db.transaction('offline_scans', 'readonly');
    const scans = await getAllFromStore(tx.objectStore('offline_scans'));
    let synced = 0;

    for (const scan of scans) {
        try {
            const response = await fetch('/api/scan/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    token_qr: scan.token_qr,
                    numero_participant: scan.numero_participant,
                    device_id: scan.device_id || 'OFFLINE_SYNC',
                }),
            });
            if (response.ok || response.status === 400 || response.status === 404) {
                const delTx = db.transaction('offline_scans', 'readwrite');
                delTx.objectStore('offline_scans').delete(scan.id);
                synced++;
            }
        } catch (e) {
            break;
        }
    }

    const clients = await self.clients.matchAll();
    clients.forEach((client) => {
        client.postMessage({ type: 'SYNC_COMPLETE', synced, total: scans.length });
    });
}

function openDB() {
    return new Promise((resolve, reject) => {
        const req = indexedDB.open('QRBadgeOffline', 1);
        req.onupgradeneeded = (e) => {
            const db = e.target.result;
            if (!db.objectStoreNames.contains('offline_scans'))
                db.createObjectStore('offline_scans', { keyPath: 'id', autoIncrement: true });
            if (!db.objectStoreNames.contains('offline_data'))
                db.createObjectStore('offline_data', { keyPath: 'token' });
        };
        req.onsuccess = (e) => resolve(e.target.result);
        req.onerror = (e) => reject(e.target.error);
    });
}

function getAllFromStore(store) {
    return new Promise((resolve, reject) => {
        const req = store.getAll();
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => reject(req.error);
    });
}

// ── Fallback page HTML for when badge page was never cached ──
const OFFLINE_BADGE_HTML = `<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Badgeage Hors Ligne</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:linear-gradient(135deg,#1A68AC 0%,#2277C1 40%,#F5B100 100%);
min-height:100vh;display:flex;align-items:center;justify-content:center;
font-family:'Segoe UI',system-ui,sans-serif;padding:1rem}
.card{background:#fff;border-radius:20px;padding:2rem;box-shadow:0 20px 60px rgba(0,0,0,.3);
width:100%;max-width:460px}
.brand{text-align:center;margin-bottom:1.5rem}
.brand h3{color:#1A68AC;font-weight:700}
.brand p{color:#718096;font-size:.9rem;margin-top:.5rem}
.offline-badge{background:#FFF8E0;border:2px solid #F5B100;border-radius:10px;
padding:.75rem;text-align:center;margin-bottom:1rem}
.form-group{margin-bottom:1rem}
label{display:block;font-weight:600;margin-bottom:.25rem;font-size:.9rem}
input{width:100%;padding:.6rem;border:1px solid #ccc;border-radius:8px;font-size:1rem}
.btn{width:100%;padding:.75rem;border:none;border-radius:10px;font-size:1.1rem;
font-weight:600;cursor:pointer;color:#fff;
background:linear-gradient(135deg,#F5B100,#E69700)}
.btn:hover{background:linear-gradient(135deg,#E69700,#BF360C)}
.result{border-radius:12px;padding:1.5rem;text-align:center;margin-bottom:1rem;display:none}
.result.show{display:block}
.result-ok{background:#f0f7ff;border:2px solid #2277C1}
.result-err{background:#fff5f5;border:2px solid #e53e3e}
.result .icon{font-size:2.5rem}
.queue{text-align:center;font-size:.85rem;color:#718096;margin-top:.5rem}
.queue b{color:#F5B100}
</style>
</head>
<body>
<div class="card">
<div class="brand">
<h3>Badgeage</h3>
<p>Mode hors ligne</p>
</div>
<div class="offline-badge">
<strong>&#x1F4F4; Pas de connexion</strong><br>
<small>Les badgeages seront synchronises au retour du reseau.</small>
</div>
<div class="result" id="r"></div>
<div class="form-group">
<label>Token QR</label>
<input type="text" id="token_qr" placeholder="UUID du QR code">
</div>
<div class="form-group">
<label>Numero participant / formateur</label>
<input type="text" id="numero" placeholder="Ex: P001 ou F001" autofocus>
</div>
<button class="btn" id="btn" onclick="doScan()">Badger (hors ligne)</button>
<div class="queue" id="qinfo"></div>
</div>
<script>
const DB='QRBadgeOffline',V=1,S='offline_scans';
function odb(){return new Promise((ok,ko)=>{const r=indexedDB.open(DB,V);
r.onupgradeneeded=e=>{const d=e.target.result;
if(!d.objectStoreNames.contains(S))d.createObjectStore(S,{keyPath:'id',autoIncrement:true});
if(!d.objectStoreNames.contains('offline_data'))d.createObjectStore('offline_data',{keyPath:'token'});};
r.onsuccess=e=>ok(e.target.result);r.onerror=e=>ko(e.target.error)})}
async function cnt(){const d=await odb();return new Promise(ok=>{
const r=d.transaction(S,'readonly').objectStore(S).count();
r.onsuccess=()=>ok(r.result);r.onerror=()=>ok(0)})}
async function add(s){const d=await odb();return new Promise((ok,ko)=>{
const t=d.transaction(S,'readwrite');t.objectStore(S).add(s);
t.oncomplete=()=>ok();t.onerror=e=>ko(e.target.error)})}
async function lookupPersonne(num){
try{const d=await odb();return new Promise((ok)=>{
const t=d.transaction('offline_data','readonly');
const r=t.objectStore('offline_data').getAll();
r.onsuccess=()=>{const all=r.result;
for(const f of all){const upper=num.toUpperCase();
const p=[...f.participants,...f.formateurs].find(x=>x.numero===upper);
if(p)return ok(p)}ok(null)};r.onerror=()=>ok(null)})}catch(e){return null}}
(function(){const p=new URLSearchParams(location.search);const t=p.get('token');
if(t)document.getElementById('token_qr').value=t})();
async function doScan(){
const token=document.getElementById('token_qr').value.trim();
const num=document.getElementById('numero').value.trim();
const res=document.getElementById('r');
if(!token||!num){res.className='result show result-err';
res.innerHTML='<div class="icon">&#x26A0;</div><p>Token et numero requis</p>';return}
await add({token_qr:token,numero_participant:num,device_id:'OFFLINE_WEB',
timestamp_local:new Date().toISOString()});
const personne=await lookupPersonne(num);
const h=new Date().toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit'});
let info=num;
if(personne)info=personne.prenom+' '+personne.nom+' ('+personne.numero+')';
res.className='result show result-ok';
res.innerHTML='<div class="icon">&#x1F4E6;</div><h4>Sauvegarde hors ligne</h4>'
+'<p><b>'+info+'</b></p><p style="color:#718096;font-size:.85rem">'+h
+' - sera synchronise automatiquement</p>';
document.getElementById('numero').value='';document.getElementById('numero').focus();
const c=await cnt();document.getElementById('qinfo').innerHTML=
'<b>'+c+'</b> badgeage(s) en attente de synchronisation';
if('serviceWorker' in navigator&&'SyncManager' in window){
const reg=await navigator.serviceWorker.ready;reg.sync.register('sync-scans').catch(()=>{})}}
cnt().then(c=>{if(c>0)document.getElementById('qinfo').innerHTML=
'<b>'+c+'</b> badgeage(s) en attente de synchronisation'});
window.addEventListener('online',()=>{location.reload()});
</script>
</body></html>`;

