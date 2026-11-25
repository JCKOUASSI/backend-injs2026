# 01 — Périmètre et méthode

## 1. Objet de l'audit

Évaluer la **qualité technique réelle** du système SYGET (gestion de la scolarité, des ressources humaines et des présences de l'INJS), telle qu'elle ressort du dépôt de code, de sa configuration et de ses chaînes d'intégration et de déploiement — et non des intentions exprimées dans la documentation.

Quatre questions ont guidé les investigations :

1. **Le système est-il sûr ?** Qui peut appeler quoi, avec quels secrets, et que se passe-t-il en cas d'abus ?
2. **Le système est-il maintenable ?** Où sont les points de rupture (fichiers géants, duplication, couplage), et un nouvel arrivant peut-il travailler sans crainte de tout casser ?
3. **Le système est-il vérifié ?** Les tests couvrent-ils ce qui compte, et tournent-ils assez vite pour être exécutés ?
4. **Le système est-il livrable ?** La chaîne CI → images → production protège-t-elle réellement contre une régression ou une manipulation destructrice ?

## 2. Périmètre

### Inclus

| Sous-système | Emplacement | Volumétrie mesurée |
|---|---|---|
| API / métier | `backend/` (23 applications Django installées) | 819 fichiers `.py`, 189 787 lignes (hors migrations, hors `.venv`), 176 modèles, 312 migrations, 1 254 routes documentées |
| Interface web | `frontend/` (React 18 + Vite 7) | 365 fichiers `.js`/`.jsx`, 118 755 lignes, 147 routes |
| Application mobile | `qr_badge_mobile/` (Flutter) | 43 fichiers `.dart`, 8 116 lignes, 3 fichiers de test |
| Intégration continue | `.github/workflows/` (5 workflows) | CI backend/frontend, publication d'images, déploiement, aperçu mobile |
| Déploiement | `deploy/production/`, `docker/` | compose à 4 services, `deploy.sh` garde-foué, runbook, workflow de déploiement |

### Exclu

- **La production** (`injs.badge-qr-code.pro`) : aucun accès au serveur, à la base réelle, aux journaux d'exploitation ni aux sauvegardes.
- **Les journaux d'exécution GitHub Actions** : non récupérables depuis cet environnement ; les causes d'échec ont été déduites des **métadonnées de jobs** exposées par l'API GitHub (nom de l'étape en échec) et reproduites localement.
- **Les performances de production** (latence, charge réelle) : seules les performances de compilation et d'exécution locale ont été mesurées.
- **Le contenu métier** (pertinence des référentiels, exactitude des maquettes) : hors périmètre d'un audit technique.

## 3. Méthode

### 3.1 Analyse statique et cartographie

- Inventaire des applications, modèles, migrations, vues et routes à partir du code et du schéma OpenAPI généré (`manage.py spectacular --validate`).
- Recherche systématique de motifs à risque : `AllowAny`, `@api_view` sans permission, `eval`, `exec`, `os.system`, `subprocess`, `shell=True`, SQL brut (`.raw(`, `extra(`), `mark_safe`, `pickle`, `verify=False`, `print()` en code de production.
- Recherche de secrets versionnés : `.env`, `*.sqlite3`, clés, certificats, artefacts.

### 3.2 Exécution de contrôles fournis par le projet

| Contrôle | Résultat |
|---|---|
| `manage.py check` | aucune erreur |
| `manage.py check --deploy` (DEBUG=0, clé longue) | **1 avertissement** `security.W008` (`SECURE_SSL_REDIRECT=False`, choix documenté) |
| `manage.py makemigrations --check --dry-run` | aucune dérive de schéma |
| `manage.py check_repo_hygiene` | **code de sortie 1** — 1 fichier interdit suivi |
| `manage.py spectacular --validate` | schéma valide (1 254 routes) |
| Tests backend (périmètre scolarité + référentiels) | 686 tests, 2 ignorés, ≈ 116 s ; `scolarite` seule : 555 tests, 92,5 s |
| Tests frontend (suite complète) | 2 258 tests / 144 fichiers, 120,5 s |
| `npm run lint` | 0 erreur, 7 avertissements |
| `vite build` | succès, bundle initial 1 668,66 Ko (398,30 Ko gzip) |
| `npm audit --omit=dev` | 3 vulnérabilités modérées (`react-router`) |

### 3.3 Lecture croisée de la chaîne de livraison

- Contenu des 5 workflows, déclencheurs, permissions, secrets utilisés.
- Historique des exécutions CI via l'API GitHub (`gh run list`, `gh api .../jobs`) : conclusion, branche, étape fautive.
- Analyse du compose de production, du runbook et du garde-fou de `deploy.sh`.

## 4. Échelle de gravité employée

| Niveau | Définition |
|---|---|
| **Bloquant** | empêche de garantir la qualité ou la livraison ; à traiter immédiatement |
| **Élevé** | risque de sécurité réel, ou perte de capacité de détection d'une régression |
| **Moyen** | dette qui ralentit durablement les évolutions ou dégrade l'expérience |
| **Faible** | amélioration d'hygiène, sans risque direct |

Effort : **S** (< 1 jour), **M** (1 à 5 jours), **L** (> 5 jours).

## 5. Limites et précautions de lecture

1. **Les mesures de tests locales** ont été exécutées sur SQLite (profil de bac à sable) pour le sous-ensemble scolarité/référentiels ; la CI, elle, tourne sur PostgreSQL. Les durées observées ici sont donc **indicatives** et plutôt optimistes.
2. **L'historique CI** est lu à travers les métadonnées GitHub ; le détail des journaux n'était pas accessible. La cause racine de l'échec a néanmoins été **reproduite localement** par la commande d'hygiène (code de sortie 1) et recoupée avec le contenu du workflow.
3. **Aucune intrusion, aucun test de charge, aucune analyse dynamique** de l'application en production n'a été réalisé.
4. Les constats portent sur l'état du dépôt au commit `8245d9c` ; un correctif postérieur peut les invalider — la section « plan d'action » indique comment vérifier chaque correction.

## 6. Reproductibilité

Toutes les commandes et sorties significatives sont consignées dans `annexes/preuves-et-commandes.md`, afin qu'un tiers puisse refaire les mesures et contester un chiffre.
