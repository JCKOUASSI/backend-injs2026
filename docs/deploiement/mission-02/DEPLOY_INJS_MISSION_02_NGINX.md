# DEPLOY-INJS-2026 — Mission 02 — Reverse proxy nginx (configuration candidate)

**Projet :** INJS Abidjan — `backend-injs2026`
**Date du rapport :** 06 novembre 2026
**Périmètre :** §8 — durcissement du gateway placé derrière Nginx Proxy Manager
**Statut :** **configuration candidate livrée — NON appliquée**. Aucune
modification n'a été effectuée sur le VPS ni dans `docker/nginx/default.conf`.

---

## 1. Chaîne réelle examinée

```
Internet ──HTTPS──► Nginx Proxy Manager (TLS, injs.badge-qr-code.pro)
                        │  HTTP sur le réseau Docker
                        ▼
                 gateway nginx (docker/nginx/default.conf)
                   ├── /        → frontend:80   (React/Vite)
                   ├── /api/    → backend:8000  (Django)
                   ├── /admin/  → backend:8000  (Django admin)
                   ├── /static/ → volume staticfiles
                   └── /media/  → volume media
```

Configuration actuelle lue intégralement : `docker/nginx/default.conf` (49 lignes).

---

## 2. Anomalies constatées dans la configuration actuelle

### A. `X-Forwarded-Proto` écrasé — incohérence HTTPS / cookies / CSRF

Configuration actuelle, répétée dans **tous** les blocs :

```nginx
proxy_set_header X-Forwarded-Proto $scheme;
```

Or NPM **termine le TLS** : il parle à ce gateway en HTTP. `$scheme` vaut donc
toujours `http`, et l'en-tête `X-Forwarded-Proto: https` posé par NPM est
**remplacé** par `http`.

Côté Django, `backend/config/settings.py` (bloc `if not DEBUG`) :

```python
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE   = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
```

Django ne voit donc **jamais** `https`. Conséquences concrètes : détection du
schéma fausse pour `request.is_secure()`, génération d'URL absolues en `http://`,
et comportements CSRF dépendants du schéma incohérents avec le navigateur.

### B. `/admin/` exposé publiquement

Aucune restriction d'adresse : l'administration Django (inscriptions, décisions
de jury, données personnelles) est joignable depuis Internet, protégée par le
seul mot de passe.

### C. `client_max_body_size` absent

ngnix applique alors son défaut de **1 Mo**. Or `backend/core/validators.py`
autorise :

```python
TAILLE_MAX_PIECE  = 10 * 1024 * 1024   # 10 Mio — pièces de candidature
TAILLE_MAX_PREUVE =  5 * 1024 * 1024   #  5 Mio — preuves de paiement
```

Toute pièce entre 1 et 10 Mio est donc refusée par nginx avec un **413 opaque**,
alors que Django l'aurait acceptée avec un message clair. Les imports Excel
(openpyxl) sont concernés de la même façon.

### D. En-têtes de sécurité absents

Ni `X-Content-Type-Options`, ni `Referrer-Policy`, ni `Permissions-Policy`.

---

## 3. Configuration candidate

Fichiers livrés :

* `deploy/production/nginx/injs-lmd.candidate.conf` — bloc `server` complet ;
* `deploy/production/nginx/injs-admin-allowlist.conf.example` — modèle de liste
  d'accès à `/admin/` (refus par défaut, sans adresse réelle).

### 3.1 Correction A — protocole réel conservé

```nginx
map $http_x_forwarded_proto $injs_forwarded_proto {
    default $http_x_forwarded_proto;
    ""      $scheme;
}
…
proxy_set_header X-Forwarded-Proto $injs_forwarded_proto;
```

* si NPM fournit l'en-tête → il est **conservé** (`https`) ;
* sinon (sonde interne, accès direct en HTTP) → repli sur `$scheme`.

### 3.2 Correction B — administration non exposée par défaut

```nginx
location /admin/ {
    include /etc/nginx/conf.d/injs-admin-allowlist.conf;
    …
}
```

Le fichier inclus contient `deny all;` tant qu'aucune décision n'a été prise.
Deux politiques documentées :

| Option | Usage | Contenu de la liste |
|---|---|---|
| 1 — plage d'administration INJS | accès depuis le site et les postes habilités | `allow <plage>; allow <IP>; deny all;` |
| 2 — tunnel/VPN uniquement | aucune exposition publique | `deny all;` (état par défaut livré) |

`allow all;` est explicitement interdit par le modèle.

Les chemins `/api/`, `/static/`, `/media/` et `/` (SPA) **ne sont pas
restreints** : le front, le scan QR depuis les téléphones et les API publiques
continuent de fonctionner.

### 3.3 Correction C — `client_max_body_size` dimensionné, pas arbitraire

```nginx
client_max_body_size 12m;
```

Justification chiffrée à partir du code, non d'une intuition :

| Élément | Limite réelle | Source |
|---|---|---|
| Pièces de candidature | 10 Mio | `backend/core/validators.py` → `TAILLE_MAX_PIECE` |
| Preuves de paiement | 5 Mio | `backend/core/validators.py` → `TAILLE_MAX_PREUVE` |
| Imports Excel | quelques Mo | `formations/api_views.py` (`load_workbook`) |

**12 Mio = 10 Mio (limite métier la plus haute) + enveloppe multipart.**

Pourquoi pas 10 Mio : certaines pièces valides échoueraient en 413 à cause du
surcoût multipart. Pourquoi pas 100 Mio : exposition inutile. L'effet recherché
est que **Django** refuse proprement un fichier trop gros (message explicite),
et non que nginx renvoie une erreur opaque.

### 3.4 Correction D — en-têtes et journalisation

```nginx
add_header X-Content-Type-Options "nosniff" always;
add_header X-Frame-Options "SAMEORIGIN" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
add_header Permissions-Policy "geolocation=(self), camera=(self), microphone=()" always;
```

`geolocation` et `camera` restent autorisés pour l'origine : ils sont
**nécessaires** au badgeage QR géolocalisé. `microphone` est refusé.

S'ajoutent : `upstream` avec `keepalive`, délais de proxy explicites
(120 s pour `/api/` — imports Excel et générations PDF), logs dédiés, et une
sonde `GET /nginx-health` pour les contrôles de bascule.

---

## 4. Validation réalisée et limites

| Contrôle | Résultat |
|---|---|
| Équilibre des accolades du fichier candidate | **OK** |
| 1 bloc `server`, 8 blocs `location`, 1 `map` | **OK** |
| `client_max_body_size` présent, valeur `12m` | **OK** |
| `X-Forwarded-Proto` pointant sur la `map` (et non `$scheme`) | **OK** |
| `nginx -t` (test de syntaxe réel) | **NON EXÉCUTÉ — binaire `nginx` absent de la sandbox, installation impossible** |
| Test HTTPS / redirections / cookies / CSRF réels | **NON EXÉCUTÉ — nécessite le VPS (mission 03)** |

Ces deux derniers points sont donc à exécuter **avant** toute bascule :

```sh
docker run --rm -v "$PWD/deploy/production/nginx:/etc/nginx/conf.d:ro" \
  nginx:1.27-alpine nginx -t
```

---

## 5. Procédure d'application (à exécuter en mission 03, jamais maintenant)

1. **Sauvegarder** la configuration en place :
   `cp docker/nginx/default.conf docker/nginx/default.conf.bak-$(date +%Y%m%d-%H%M%S)`
2. Générer la liste d'accès à partir du modèle :
   `cp deploy/production/nginx/injs-admin-allowlist.conf.example /etc/injs/injs-admin-allowlist.conf`
   puis y inscrire les adresses **validées par le commanditaire**.
3. Monter la candidate et la liste dans le service `gateway`
   (adapter les deux volumes du compose), sans toucher aux autres services.
4. Tester la syntaxe **avant** rechargement : `nginx -t` dans le conteneur.
5. Recharger : `docker compose exec gateway nginx -s reload`.
6. Vérifier, dans cet ordre :
   * `https://injs.badge-qr-code.pro/` → SPA (200) ;
   * `/api/health/` → 200 et `request.is_secure()` vrai côté Django ;
   * un upload de 9 Mio (pièce de candidature) → accepté ;
   * un upload de 11 Mio → refus **Django** avec message, pas 413 nginx ;
   * `/admin/` depuis une IP non autorisée → 403 ;
   * cookie de session avec l'attribut `Secure` ;
   * connexion + une action POST (CSRF) de bout en bout.
7. En cas d'écart : restaurer le `.bak` et recharger.

**Aucune de ces étapes n'a été exécutée.** La configuration reste candidate.
