# Recréer la démo Arena sur macOS, sans toucher au VPS

Le dépôt **contient les scripts** et jeux de données sources (`arena/remplir-base-locale.py`, `backend/seed_data.py`, commandes `seed_*`, `completer_capture_dashboard_demo`) mais **pas** `backend/db.sqlite3` : ce fichier est ignoré par Git, même dans cette session. La base locale de la session a été contrôlée en lecture seule : **5 037 participants**, **5 027 dossiers étudiants** et **93 formateurs**. Ces effectifs comprennent 5 000 profils fictifs inscrits et des dossiers complémentaires. Le script ci-dessous reconstruit cette cohorte de manière déterministe à partir d'une base neuve, puis contrôle les trois effectifs ; il **ne copie pas bit à bit** la base Arena, les éventuelles saisies manuelles, les médias privés ni les mots de passe de session. Les dates dépendantes du jour de lancement peuvent varier.

## Conditions de sécurité

**Uniquement sur votre Mac et un clone neuf** du dépôt ; jamais sur `152.228.233.123`, sur le domaine public, dans un conteneur de production ou sur une base PostgreSQL. Le script refuse une base SQLite existante et les `.env` non marqués `INJS_LOCAL_DEMO_ONLY`. Il crée `backend/.env` et `frontend/.env` privés, force SQLite à `backend/db.sqlite3` et limite les origines/hôtes à `localhost`. Les comptes de démonstration possèdent des mots de passe connus : **ne pas exposer** le serveur local à Internet ou au réseau local, ne jamais transférer sa base et ne pas lancer `seed_data.py` sur une base réelle. Si une base locale existe déjà, **ne pas la supprimer** : conserver ses données et utiliser un second clone neuf pour la démo.

## Terminal macOS

Si la copie locale est déjà dans `~/injs-arena-source`, vérifier d'abord qu'elle contient le dernier script de la branche (GitHub sert ici **uniquement de transport du code**, pas de déploiement) :

```sh
cd "$HOME/injs-arena-source"
git pull --ff-only origin arena/a8060ecf-backend-injs2026
ls scripts/preparer-demo-macos.sh arena/remplir-base-locale.py backend/core/management/commands/completer_capture_dashboard_demo.py
bash scripts/preparer-demo-macos.sh --check
```

Si `--check` refuse une base ou un `.env` déjà présent, **ne contournez pas le refus**. Une copie séparée, vide et sans `.env`, est requise. Python **3.10 à 3.13** et Node.js **20.19+ ou 22.12+** sont nécessaires. Le script crée un venv Python et installe les dépendances via pip, puis `npm ci` pour le front. Prévoir une connexion réseau et du temps pour environ 5 000 profils fictifs.

Après avoir confirmé que le chemin affiché est `.../injs-arena-source/backend/db.sqlite3` **sur le Mac** et n'existe pas encore :

```sh
bash scripts/preparer-demo-macos.sh --apply --confirm-local-demo
```

Le script applique les migrations, importe les référentiels et maquettes du dépôt, crée la cohorte initiale **3 500**, vérifie sa composition (67 formateurs et 130 groupes sans charge), sauvegarde la SQLite privée dans `backups/`, puis complète à **5 000** et vérifie les **5 037** participants. Une erreur stoppe la chaîne ; ne pas « réparer » avec un seed de 5 000 sur la cohorte de 3 500, qui la mélangerait.

Pour l'utiliser, ouvrir **deux terminaux** dans le même clone :

```sh
# Terminal 1 — API Django, seulement sur l'interface locale du Mac :
cd "$HOME/injs-arena-source/backend"
./.venv/bin/python manage.py runserver 127.0.0.1:8000
```

```sh
# Terminal 2 — application web et proxy /api vers 127.0.0.1:8000 :
cd "$HOME/injs-arena-source/frontend"
npm run dev -- --host 127.0.0.1
```

Ouvrir <http://127.0.0.1:3000> sur le Mac. Ne pas utiliser `arena/reconstruire.sh` pour cette étape : il active un **profil d'aperçu iframe Arena** et sa première passe crée 3 500 étudiants, pas les 5 037 de la capture. Ne pas interpréter les chiffres de la démo comme des étudiants officiels.
