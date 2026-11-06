# MISSION 02 — DURCISSEMENT DE LA PASSERELLE NGINX (CANDIDAT)

**Date** : 6 novembre 2026 · **Branche** : `arena/4524a57c-backend-injs2026`
**Fichier concerné** : `docker/nginx/default.conf` (monté en lecture seule par
le service `gateway` de `deploy/production/compose.yml`)

> **Configuration candidate livrée, non appliquée.** Aucune modification n'a
> été faite sur le VPS, et Nginx Proxy Manager n'a pas été touché. La procédure
> d'application figure au §5.

---

## 1. ARCHITECTURE ET FLUX DES EN-TÊTES

```
Navigateur ──HTTPS──► Nginx Proxy Manager (TLS, certificat, port 443)
                            │  HTTP interne + X-Forwarded-Proto: https
                            ▼
                     Passerelle gateway (nginx:1.27-alpine, port 8080 publié)
                            │  HTTP + en-têtes relayed
                            ▼
                ├─ /          → frontend (nginx, SPA)
                ├─ /api/      → backend Django (gunicorn 8000)
                ├─ /admin/    → backend Django — FERMÉ par défaut
                ├─ /static/   → volume staticfiles
                └─ /media/    → volume média
```

Côté Django (`backend/config/settings.py`) :

| Réglage | Valeur | Cohérence |
|---|---|---|
| `SECURE_PROXY_SSL_HEADER` | `('HTTP_X_FORWARDED_PROTO', 'https')` | Django se fie à l'en-tête relayé |
| `SECURE_SSL_REDIRECT` | `False` (**volontaire**) | la redirection est faite par NPM ; l'activer bouclerait |
| `SESSION_COOKIE_SECURE` / `CSRF_COOKIE_SECURE` | `True` hors DEBUG | cookies jamais émis en clair |
| `CSRF_TRUSTED_ORIGINS` | `https://injs.badge-qr-code.pro` | référent HTTPS accepté |
| `SECURE_HSTS_SECONDS` | 1 an (+ sous-domaines, préchargement) | émis une fois la requête jugée sûre |

## 2. CORRECTIONS APPORTÉES

### A. `X-Forwarded-Proto` n'est plus écrasé

**Avant** (anomalie de l'audit) :

```nginx
proxy_set_header X-Forwarded-Proto $scheme;    # $scheme vaut « http » ici
```

Dans le conteneur passerelle, la connexion NPM → passerelle est **toujours en
HTTP** : la directive écrasait donc `https` par `http`, quelle que soit la
requête publique. Django voyait une requête non sécurisée
(`request.is_secure() == False`), ce qui peut fausser la génération d'URL
absolues, les contrôles CSRF et le comportement HSTS.

**Après** :

```nginx
map $http_x_forwarded_proto $proto_public {
    default  $http_x_forwarded_proto;   # on conserve ce qu'annonce NPM
    ''       $scheme;                   # repli si NPM ne transmet rien
}
...
proxy_set_header X-Forwarded-Proto $proto_public;
```

Chaîne complète désormais cohérente : HTTPS public → `X-Forwarded-Proto: https`
conservé → Django considère la requête sûre → cookies `Secure` acceptés →
contrôle CSRF sur référent HTTPS → HSTS émis.

### B. `/admin/` fermée par défaut

```nginx
    location /admin/ {
        # allow 41.0.0.0/16;   # << IP/plage à renseigner par l'exploitant
        # allow 10.8.0.0/24;   # exemple : plage VPN
        deny all;

        proxy_pass http://backend:8000;
    }
```

* principe : **fermé par défaut**, ouverture explicite par liste blanche d'IP ;
* aucune incidence sur `/api/`, `/static/`, `/media/` (le frontend continue de
  fonctionner normalement) ;
* alternative si l'exploitant préfère : ne pas exposer `/admin/` du tout dans
  NPM, ou exiger une authentification supplémentaire côté NPM.

### C. `client_max_body_size` justifié

Valeur retenue : **25 Mio**.

| Source | Limite |
|---|---|
| `backend/core/validators.py` — `TAILLE_MAX_PIECE` | 10 Mio (pièce de dossier : PDF/JPEG/PNG) |
| `backend/core/validators.py` — `TAILLE_MAX_PREUVE` | 5 Mio (preuve de paiement) |
| `DATA_UPLOAD_MAX_NUMBER_FIELDS` | 5 000 champs |

Pire cas réaliste : une requête multipart portant **une pièce et une preuve**
→ 15 Mio de fichiers, + encodage multipart, en-têtes et champs (~10 %) ≈ 17 Mio.
**25 Mio** couvre ce cas avec une marge raisonnable, tout en bornant l'exposition.
Un test automatisé vérifie que la valeur du fichier reste ≥
`TAILLE_MAX_PIECE + TAILLE_MAX_PREUVE` : la limite suivra donc toute évolution
des validateurs applicatifs.

### D. Divers

* sonde locale `location = /nginx-health` (non exposée publiquement) ;
* en-têtes de proxy mutualisés en tête de bloc `server` (plus de risque
  d'oubli sur une nouvelle `location`) ;
* montage du fichier de configuration en lecture seule (`:ro`) — conservé.

## 3. VALIDATION EFFECTUÉE (statique — aucun nginx dans l'environnement)

**Fichier créé** : `backend/config/tests/test_nginx_gateway.py` — **13 tests**,
tous au vert.

| Contrôle | Test |
|---|---|
| `$scheme` ne remplace plus le protocole public | `test_le_scheme_local_ne_remplace_plus_le_protocole_public` |
| La `map` relaie l'en-tête de NPM | `test_le_protocole_transmis_par_le_proxy_est_relaye`, `test_le_repli_utilise_le_scheme_de_la_connexion_entrante` |
| `/admin/` fermée, jamais `allow all;` (vérifié **hors commentaires**) | `test_admin_est_fermee_par_defaut`, `test_admin_n_est_jamais_ouverte_a_tous` |
| API et fichiers statiques intacts | `test_les_api_du_frontend_restent_accessibles`, `test_static_et_media_restent_servis` |
| `client_max_body_size` défini, ≥ pire cas applicatif, et borné | `test_client_max_body_size_est_defini_explicitement`, `test_la_taille_couvre_le_pire_cas_applicatif`, `test_la_taille_reste_bornee` |
| Structure et câblage Compose (fichier monté, en `:ro`) | `test_accolades_equilibrees`, `test_le_fichier_est_celui_monte_par_le_compose`, `test_le_montage_est_en_lecture_seule` |

**Limite assumée** : `nginx -t` et les essais HTTPS/CSRF/cookies exigent le
serveur ; ils relèvent de la procédure d'application (§5).

## 4. PROCÉDURE D'APPLICATION SUR LE VPS (à valider par l'exploitant)

```bash
# 1. Déposer la configuration candidate (rien n'est écrasé sans sauvegarde)
cp docker/nginx/default.conf /opt/injs/injs-gateway/default.conf

# 2. Adapter le montage ou recopier dans l'arborescence attendue par le compose
#    (le compose monte ../../docker/nginx/default.conf en lecture seule)

# 3. Ouvrir /admin/ SI et seulement si l'exploitant le décide :
#    décommenter une ligne `allow <IP ou plage>` dans le bloc location /admin/

# 4. Vérifier la syntaxe AVANT rechargement
docker compose -f deploy/production/compose.yml exec gateway nginx -t

# 5. Recharger sans coupure
docker compose -f deploy/production/compose.yml exec gateway nginx -s reload
```

## 5. CONTRÔLES À RÉALISER APRÈS APPLICATION (liste de vérification)

| # | Contrôle | Commande / observation | Attendu |
|---|---|---|---|
| 1 | Syntaxe | `nginx -t` | `syntax is ok` |
| 2 | HTTPS public | `curl -I https://injs.badge-qr-code.pro/` | `200`, certificat valide |
| 3 | Redirection HTTP → HTTPS | `curl -I http://injs.badge-qr-code.pro/` | `301` vers `https://` |
| 4 | Protocole relayé | `curl -s https://injs.badge-qr-code.pro/api/health/` puis vérifier côté Django `request.is_secure()` | `True` |
| 5 | En-têtes de proxy | `docker compose logs backend` (ou une vue de diagnostic) | `X-Forwarded-Proto: https` |
| 6 | Cookies sécurisés | inspecteur du navigateur sur `/api/auth/login/` | `Secure`, `HttpOnly`, `SameSite` |
| 7 | CSRF | soumission d'un formulaire authentifié | `403` si en-tête absent, `200/201` si présent |
| 8 | API frontend | parcours Scolarité / Formations / EDT | aucune erreur réseau, pas de 502 |
| 9 | Administration depuis une IP non autorisée | `curl -I https://injs.badge-qr-code.pro/admin/` | `403` |
| 10 | Administration depuis une IP autorisée | idem après ouverture | page de connexion Django |
| 11 | Téléversement limite | envoyer une pièce de 10 Mio via le formulaire concerné | accepté (limite applicative) |
| 12 | Téléversement au-delà | envoyer 30 Mio | rejeté par nginx (`413`) avant Django |

Toute anomalie constatée sur ces douze points doit être documentée avant
bascule définitive du trafic.

## 6. POINTS LAISSÉS À LA DÉCISION DE L'EXPLOITANT

* ouverture ou non de `/admin/`, et selon quelle liste d'IP ;
* exposition publique de la sonde `/nginx-health` (à proscrire) ;
* ajout éventuel d'en-têtes de sécurité (`X-Content-Type-Options`,
  `Referrer-Policy`, CSP) au niveau NPM — non obligatoire pour la levée des
  blocages, mais recommandé à terme.

## 7. FICHIERS

| Fichier | Statut |
|---|---|
| `docker/nginx/default.conf` | **modifié** (sauvegarde : version précédente dans l'historique Git, commit `08e2f4e`) |
| `backend/config/tests/test_nginx_gateway.py` | **créé** — 13 tests |

Aucun fichier supprimé. Aucune modification sur le VPS.
