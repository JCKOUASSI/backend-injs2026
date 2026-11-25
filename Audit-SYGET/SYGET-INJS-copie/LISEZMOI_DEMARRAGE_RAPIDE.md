# COPIE OPÉRATIONNELLE CLÉ EN MAIN — SYGET-INJS (INJS Abidjan)

Cette archive constitue **une copie complète, préconfigurée et immédiatement exploitable** de l'application **SYGET-INJS**, incluant :
1. L'intégralité de l'application web Django 5 (`apps/`, `config/`, `shared/`, `templates/`, `static/`, `docs/`).
2. La base de données SQLite pré-initialisée (`test.sqlite3`) contenant le jeu de données complet INJS Abidjan :
   - **1 Formation active** : *Formation Continue des Cadres Sportifs — Session INJS* (Vague `2026-A`, 4 modules, 48h/groupe)
   - **40 Auditeurs** inscrits (grades A3 et A4) répartis automatiquement en **3 Groupes** (`A3_GROUPE1`, `A3_GROUPE2`, `A4_GROUPE1`)
   - **6 Formateurs** spécialisés affectés en Unité Pédagogique
   - **2 Sites, 3 Bâtiments, 6 Salles** (Campus INJS Marcory & Annexe)
   - **36 Séances** planifiées sans aucune collision de salle ni de formateur
   - **1 Scénario de simulation** sauvegardé
3. Une sauvegarde portable des données au format JSON (`fixtures/donnees_completes_syget_injs.json`) rechargeable dans PostgreSQL (`python manage.py loaddata fixtures/donnees_completes_syget_injs.json`).
4. Le fichier `.env` préconfiguré (`DJANGO_USE_SQLITE=1`) et les scripts de lancement automatique :
   - Sous **macOS / Linux** : `./demarrer_syget.sh`
   - Sous **Windows** : double-clic sur `demarrer_syget.bat`
   - Avec **Docker Compose (PostgreSQL)** : `docker compose up --build`
5. Le manuel de fonctionnement (`Manuel_Fonctionnement_SYGET_INJS.pdf`).

## Connexion immédiate
- **URL locale** : `http://127.0.0.1:8000/login/`
- **Identifiant Administrateur** : `admin`
- **Mot de passe** : `admin`
- **Compte Responsable UP (RUP)** : `rup_pedago` / `rup2026!`
