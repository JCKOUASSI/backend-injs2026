# Sauvegarde et restauration

Point de restauration créé le **2026-10-28**, avant de nouvelles modifications.
État sauvegardé : `7ca2476` (arbre propre, CI verte).

## 1. Ce qui a été sauvegardé

| Élément | Emplacement | Rôle |
|---|---|---|
| Tag Git `sauvegarde-2026-10-28` | dépôt + GitHub (poussé) | revenir au code exact en une commande |
| `injs-backend-2026-10-28.bundle` | `~/sauvegardes/2026-10-28_avant-modifications/` | **historique complet** du dépôt dans un fichier unique (9,8 Mo) |
| `donnees-et-etat-de-travail.tar.gz` | idem | base SQLite `db.sqlite3` (5,5 Mo) |
| `donnees-metier.json` | idem | export **portable** des données (1 454 objets, 20 modèles), rechargeable sur PostgreSQL |
| `environnement-python.txt` | idem | 34 paquets figés (`pip freeze`) |
| `environnement-outils.txt` | idem | python 3.11.2 · node v22.22.3 · npm 10.9.8 |
| `SHA256SUMS.txt` | idem | empreintes de tous les fichiers ci-dessus |

Le fichier `backend/.env` n'est **pas** sauvegardé : il contient le mot de passe de
démonstration et se régénère par `bash arena/bootstrap.sh --write-env`.
`backend/.venv`, `frontend/node_modules` et `backend/staticfiles` ne sont pas
sauvegardés non plus : ce sont des artefacts de construction, reproductibles
(§3.4).

## 2. Vérifications effectuées sur la sauvegarde

Une sauvegarde non testée n'est pas une sauvegarde. Les contrôles suivants ont
été exécutés :

| Test | Résultat |
|---|---|
| `git bundle verify` | « The bundle records a complete history » |
| Références contenues | branche de travail, `main`, tag de sauvegarde, `HEAD` |
| `PRAGMA integrity_check` sur la base extraite | **ok** — 204 tables, 20 comptes |
| `loaddata` du JSON dans une base **neuve** | **1 454 objets installés** |
| Fidélité (comptages original vs restauré) | **aucun écart** sur 10 modèles témoins |
| Empreintes SHA-256 | vérifiables par `sha256sum -c SHA256SUMS.txt` |

## 3. Procédures de restauration

### 3.1 Revenir au code sauvegardé (cas courant)

```bash
cd backend-injs2026
git fetch --tags origin
git switch --detach sauvegarde-2026-10-28   # consultation
# ou, pour repartir proprement de cet état :
git switch -c reprise-depuis-sauvegarde sauvegarde-2026-10-28
```

Aucune perte : le tag pointe une révision immuable. Pour annuler une modification
non commitée, préférer `git restore <fichier>` ; **ne jamais** utiliser
`git reset --hard` (règle du projet).

### 3.2 Restaurer les données d'une base SQLite

```bash
# sauvegarde de sécurité de la base actuelle, d'abord
cp backend/db.sqlite3 backend/db.sqlite3.avant-restauration

tar -xzf ~/sauvegardes/2026-10-28_avant-modifications/donnees-et-etat-de-travail.tar.gz \
    -C .
```

### 3.3 Restaurer les données sur un autre moteur (PostgreSQL)

```bash
cd backend
.venv/bin/python manage.py migrate
.venv/bin/python manage.py loaddata \
    ~/sauvegardes/2026-10-28_avant-modifications/donnees-metier.json
```

L'export exclut volontairement `contenttypes`, `auth.permission`, `sessions` et
`admin.logentry` : ces tables sont recréées par `migrate`.

### 3.4 Reconstruction complète (sinistre total)

**Chemin court (aperçu Arena)** — après une réinitialisation du bac à sable,
une seule commande reconstruit l'environnement, le schéma, les données de
démonstration et les référentiels officiels, puis signale toute sauvegarde de
données présente dans `backups/` :

```bash
./arena/reconstruire.sh            # reconstruire (idempotent)
./arena/reconstruire.sh --verifier # contrôler l'état sans rien modifier
```

Le chemin manuel équivalent reste :

```bash
# 1) Code : depuis GitHub, ou depuis le bundle si le réseau est indisponible
git clone https://github.com/JCKOUASSI/backend-injs2026.git
#    variante hors ligne :
git clone ~/sauvegardes/2026-10-28_avant-modifications/injs-backend-2026-10-28.bundle depot
cd depot && git checkout sauvegarde-2026-10-28

# 2) Environnement backend
cd backend && python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 3) Profil d'aperçu + .env de démonstration
cd .. && bash arena/bootstrap.sh --write-env

# 4) Schéma puis données
cd backend
export PYTHONPATH="$(cd .. && pwd)" DJANGO_SETTINGS_MODULE=arena.settings_sandbox
.venv/bin/python manage.py migrate
.venv/bin/python manage.py loaddata ~/sauvegardes/2026-10-28_avant-modifications/donnees-metier.json
.venv/bin/python manage.py importer_referentiels_injs   # référentiels officiels (idempotent)
.venv/bin/python manage.py collectstatic --noinput

# 5) Site web
cd ../frontend && npm ci

# 6) Lancement
cd .. && ./arena/lancer-api.sh    # 8000
       ./arena/lancer-front.sh    # 3000
```

Sans sauvegarde de données, `python seed_data.py` puis
`manage.py importer_referentiels_injs` recréent le jeu de démonstration et les
référentiels officiels (compte `admin` / `admin123`, 8 filières, 8 cycles
LMD) — c'est ce que fait `arena/reconstruire.sh`. Le script de démarrage
`scripts/start_dev.sh` enchaîne aussi ces deux étapes automatiquement.

### 3.5 Données saisies dans l'aperçu (bac à sable éphémère)

Le bac à sable d'aperçu peut être réinitialisé à tout moment : seuls les
fichiers commités sur GitHub survivent, et `backend/db.sqlite3` est ignoré par
Git. Les données officielles et de démonstration sont reproductibles (§3.4),
mais **les saisies faites dans l'application ne le sont pas**. Pour elles :

```bash
./arena/sauvegarder-donnees.sh   # -> backups/apercu-<horodatage>/ (donnees.json,
                                 #    db.sqlite3, media, MANIFESTE, SHA256SUMS)
./arena/restaurer-donnees.sh backups/apercu-<horodatage>
```

`donnees.json` est un export portable (même périmètre qu'au §3.3), restaurable
sur SQLite comme sur PostgreSQL. La restauration commence toujours par une
copie de sécurité de la base en place.

## 4. Vérifier une sauvegarde avant de s'y fier

```bash
cd ~/sauvegardes/2026-10-28_avant-modifications
sha256sum -c SHA256SUMS.txt
git bundle verify injs-backend-2026-10-28.bundle
```

## 5. Limites à connaître

* Le bundle et les archives vivent **hors du dépôt Git**, dans `~/sauvegardes/` :
  ils ne sont pas versionnés (ce sont des artefacts volumineux) et ne suivent
  donc pas les `push`. Le **tag**, lui, est poussé sur GitHub : c'est la
  sauvegarde durable du code.
* Même règle pour les sauvegardes de l'aperçu (`backups/`, ignoré par Git) :
  le dépôt GitHub étant **public**, un export de données ne doit **jamais** y
  être commité (comptes et empreintes de mots de passe). Téléchargez la
  sauvegarde sur votre machine ; en production, la durabilité repose sur
  PostgreSQL (volume Docker) et `scripts/backup_injs_lmd.sh`.
* La base sauvegardée est celle de **démonstration** (SQLite), pas une base de
  production : aucune donnée réelle n'est concernée.
* Les fichiers téléversés (`backend/media/`) n'existaient pas au moment de la
  sauvegarde ; s'ils apparaissent, les inclure dans l'archive de données.
