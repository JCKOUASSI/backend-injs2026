# Remplir une base locale depuis VS Code / Cline

Le script téléchargeable est [`arena/remplir-base-locale.py`](../remplir-base-locale.py). Il **reconstruit** les données de démonstration à partir des commandes versionnées dans ce dépôt ; il ne contient ni ne restaure la base exacte d'une ancienne session Arena.

## Préparer le projet local

1. Récupérer cette version du dépôt, ouvrir **la racine du dépôt** dans VS Code, puis ouvrir un terminal dans Cline/VS Code.
2. Créer un environnement virtuel et installer les dépendances Python :

   - macOS / Linux : `python3 -m venv backend/.venv && backend/.venv/bin/python -m pip install -r backend/requirements.txt`
   - Windows PowerShell : `py -m venv backend/.venv; .\backend\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt`

3. Si `backend/.env` n'existe pas, copier `backend/.env.example` vers `backend/.env`. Garder `DEBUG=True` et renseigner **uniquement des identifiants locaux**. Ne jamais commiter `.env`.

## Choisir la base et lancer

Les exemples ci-dessous utilisent `python` avec le venv activé ; sinon, remplacer `python` par `backend/.venv/bin/python` (macOS/Linux) ou `.\backend\.venv\Scripts\python.exe` (Windows).

**Option simple : base SQLite de développement `backend/db.sqlite3`** (force cette base, même si `.env` mentionne PostgreSQL) :

```sh
python arena/remplir-base-locale.py --sqlite
python arena/remplir-base-locale.py --sqlite --apply --confirm-demo
```

**Option base déjà configurée dans `backend/.env`** (`USE_SQLITE=1` et `SQLITE_PATH`, ou PostgreSQL sur `localhost`) :

```sh
python arena/remplir-base-locale.py
python arena/remplir-base-locale.py --apply --confirm-demo
```

La première commande affiche la cible et les étapes **sans écrire**. Vérifier soigneusement la base affichée avant la seconde. Le script refuse `DEBUG=False`, une base SQLite hors du dépôt et PostgreSQL sur un hôte non local. Pour PostgreSQL, le client `pg_dump` doit être installé et accessible dans le `PATH`.

Avant la première écriture, une sauvegarde privée est créée dans `backups/base-locale-avant-demo-*/` si la base existe : `db.sqlite3` (SQLite, copie cohérente) ou `base.dump` (PostgreSQL, format custom). Pour une base SQLite *neuve*, il n'y a rien à sauvegarder. **Ne jamais publier ces sauvegardes** : elles peuvent contenir des comptes et des empreintes de mots de passe. Il est préférable d'arrêter le serveur Django pendant le remplissage.

La commande applique les migrations, exécute `seed_data.py`, importe les référentiels et les maquettes LMD, puis peuple candidatures, équivalences, scolarité, enseignants, stages, administration, personnel, jurys, diplômation, évaluations et finances. Elle termine par le contrôle de cohérence. Les commandes sont conçues pour être réexécutées, mais peuvent **modifier des lignes existantes**, notamment réinitialiser les mots de passe des comptes de démonstration : **ne pas utiliser sur des données réelles ou en production**.

Pour restaurer une sauvegarde SQLite, arrêter Django, copier la sauvegarde sur la base cible (en conservant d'abord une copie de sécurité de la base actuelle), puis relancer Django. Pour PostgreSQL, utiliser `pg_restore` selon la procédure de restauration adaptée à votre instance locale ; ne pas restaurer aveuglément par-dessus une base active.

### Instruction prête à copier dans Cline

> Ouvre la racine du dépôt dans VS Code. Lis `arena/documentation/REMPLIR_BASE_LOCALE_CLINE.md` et `arena/remplir-base-locale.py`. Prépare un environnement virtuel Python local et `backend/.env` en mode développement. Exécute d'abord `python arena/remplir-base-locale.py --sqlite` et montre-moi la base cible avant toute modification. Après ma confirmation explicite uniquement, exécute `python arena/remplir-base-locale.py --sqlite --apply --confirm-demo`. N'utilise jamais une base de production et ne commite ni `.env`, ni bases, ni sauvegardes.
