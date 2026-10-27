> **DOCUMENT D’ARCHIVE — NE PAS UTILISER COMME RÉFÉRENCE COURANTE.** Décrit une ancienne version du produit (badgeage QR d’époque). Référence courante : [README.md](../../README.md) et [docs/ARCHITECTURE.md](../ARCHITECTURE.md).

# Résumé de la plateforme — QR Badge MEMFPMA

## Vue d'ensemble

Plateforme de **gestion des présences par QR Code** pour le Ministère de la Fonction Publique et de la Modernisation de l'Administration (MEMFPMA), développée pour la **DFRC** (Direction de la Formation et du Renforcement des Compétences).

---

## Architecture générale

```
code-qr-badge-final/
├── backend/               # Django 6 + Django REST Framework
│   ├── config/            # Paramètres Django, URLs racine
│   ├── authentication/    # Gestion des utilisateurs, JWT, permissions
│   ├── formations/        # Formations, participants, formateurs, séances, QR tokens
│   ├── presences/         # Pointages / scans QR
│   ├── exports/           # Export PDF & Excel
│   └── dashboard/         # Page de badgeage HTML (badge.html)
├── frontend/              # React 18 + Vite (dashboard web)
│   └── src/
│       ├── pages/         # Composants pages React
│       ├── context/       # AuthContext, ToastContext
│       └── services/      # Appels API (axios)
└── qr_badge_mobile/       # App Flutter (participants / formateurs mobiles)
```

---

## Stack technique

| Couche | Technologies |
|--------|-------------|
| Backend | Django 6, Django REST Framework, SQLite |
| Auth | JWT (djangorestframework-simplejwt) |
| Frontend Web | React 18, Vite, React Router, Bootstrap Icons |
| Exports | reportlab (PDF), openpyxl (Excel) |
| Mobile | Flutter (iOS / Android) |

---

## Rôles utilisateurs

| Rôle | Accès |
|------|-------|
| **DFRC** | Accès complet — CRUD formations, participants, formateurs, utilisateurs, secrétariats |
| **DIRECTION** | Lecture seule sur toutes les données |
| **SECRETARIAT** | Gestion de ses formations et participants liés à son secrétariat |
| **SUPERVISEUR** | Démarrer / arrêter les séances de ses formations assignées, générer QR |
| **ENCADRANT** | Lecture formations + gestion séances |
| **PARTICIPANT** | Scan QR, consultation de son historique (application mobile) |

---

## Modèles de données principaux

### `Secretariat`
Entité organisationnelle (Type A / B / C) regroupant des participants et des formations.

### `Formation`
- Titre, objectif, lieu, dates, durée prévue
- Catégorie, grade, groupe, vague, programme
- Statuts : `PLANIFIEE` → `EN_COURS` → `TERMINEE` / `SUSPENDUE`
- Lié à un secrétariat, un superviseur, un créateur

### `SessionFormation`
Séance d'une journée (matin, après-midi…) liée à une formation.
- Démarrage manuel ou automatique à l'heure prévue (`auto_demarrage`)
- Durée calculée entre `demarree_le` et `terminee_le`

### `Participant`
- Numéro auto-généré (P0001…), matricule, corps, grade, groupe, vague
- Lié à un secrétariat et optionnellement à un compte utilisateur

### `Formateur`
- Numéro auto-généré (F0001…), spécialité, organisation
- Peut être rattaché à plusieurs secrétariats

### `QRToken`
- UUID unique par formation / séance
- Valide 24h, désactivé après utilisation ou expiration
- Lié optionnellement à une `SessionFormation`

### `Pointage`
- Enregistré à chaque scan QR (entrée ou sortie)
- 1er scan = ENTREE, 2e scan = SORTIE (durée calculée côté serveur)

---

## Fonctionnalités principales

### Dashboard React (frontend)
- **Tableau de bord** — statistiques globales : formations actives, terminées, participants, formateurs
- **Formations** — liste, filtres (statut, catégorie, secrétariat), création, modification, suppression
- **Détail formation** — onglets : Informations / Présences / Séances / Participants / Formateurs
- **Participants** — liste paginée, recherche, import Excel, CRUD
- **Formateurs** — liste, création, modification, suppression
- **Utilisateurs** — gestion des comptes (DFRC uniquement)
- **Secrétariats** — gestion des entités organisationnelles (DFRC uniquement)
- **Import Excel** — import en masse formations, participants, formateurs, séances

### Page de badgeage (Django — `dashboard/badge/`)
- Page HTML standalone (pas de connexion requise)
- Scan QR via caméra ou saisie manuelle du numéro participant
- Affichage du statut de pointage en temps réel
- Fonctionne hors-ligne (bannière offline)
- Toutes les autres pages Django redirigent vers le frontend React

### Application mobile Flutter
- Login JWT pour participants et formateurs
- Scanner QR code (caméra arrière)
- Anti-fraude : le numéro est déduit du compte connecté
- Historique des pointages par jour avec durées
- Configuration de l'IP serveur depuis l'app

---

## API REST — Endpoints clés

### Authentification (`/api/auth/`)
| Méthode | URL | Description |
|---------|-----|-------------|
| POST | `/api/auth/login/` | Connexion → retourne JWT access + refresh |
| POST | `/api/auth/token/refresh/` | Rafraîchir le token |
| GET | `/api/auth/me/` | Profil utilisateur connecté |

### Formations (`/api/formations/`)
| Méthode | URL | Description |
|---------|-----|-------------|
| GET/POST | `/api/formations/` | Liste / créer |
| GET/PUT/DELETE | `/api/formations/{id}/` | Détail / modifier / supprimer |
| GET | `/api/formations/list/` | Liste filtrée pour le frontend React |
| GET | `/api/formations/{id}/detail/` | Détail complet (sessions + participants) |
| POST | `/api/formations/{id}/assign-superviseur/` | Assigner un superviseur |
| POST | `/api/formations/{id}/participants/add/` | Inscrire un participant |
| POST | `/api/formations/{id}/formateurs/add/` | Assigner un formateur |
| GET | `/api/formations/stats/` | Statistiques dashboard |

### Séances
| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/api/formations/{id}/sessions/` | Liste des séances |
| POST | `/api/formations/{id}/sessions/new/` | Créer une séance |
| POST | `/api/formations/{id}/sessions/{sid}/start/` | Démarrer |
| POST | `/api/formations/{id}/sessions/{sid}/stop/` | Terminer |
| DELETE | `/api/formations/{id}/sessions/{sid}/delete/` | Supprimer |

### QR Code
| Méthode | URL | Description |
|---------|-----|-------------|
| POST | `/api/formations/{id}/generate-qr/` | Générer QR formation |
| POST | `/api/formations/{id}/sessions/{sid}/generate-qr/` | Générer QR séance |
| GET | `/api/formations/{id}/qr-image/` | Image QR (public) |

### Scan / Présences
| Méthode | URL | Description |
|---------|-----|-------------|
| POST | `/api/scan/` | Scanner QR (public, entrée ou sortie) |
| POST | `/api/scan/secure/` | Scan sécurisé anti-fraude (JWT requis) |
| GET | `/api/me/historique/` | Historique personnel |

### Exports
| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/api/exports/formation/{id}/pdf/` | Export PDF présences |
| GET | `/api/exports/formation/{id}/excel/` | Export Excel présences |

---

## Logique de scan QR

```
POST /api/scan/
{ "token_qr": "uuid", "numero_participant": "P0001", "device_id": "..." }
```
1. Vérifie token QR valide (actif, non expiré, séance non terminée)
2. Vérifie participant inscrit à la formation
3. **1er scan → ENTREE** | **2e scan → SORTIE** (durée calculée automatiquement)

---

## Responsivité

- Frontend React entièrement responsive (Bootstrap Icons + CSS custom)
- Sidebar mobile avec overlay et toggle
- Tables avec défilement horizontal (`table-container`)
- Grilles CSS adaptatives (`grid-2`, `grid-4` → 1 colonne sur mobile)
- Page de badgeage (`badge.html`) optimisée mobile-first
- Favicon présente dans l'onglet navigateur (logo MEMFPMA)

---

## URLs principales en développement

| Service | URL |
|---------|-----|
| Backend Django API | `http://localhost:8001/api/` |
| Frontend React | `http://localhost:5173/` |
| Page de badgeage | `http://localhost:8001/dashboard/badge/` |
| API Docs (Swagger) | `http://localhost:8001/api/docs/` |
| Admin Django | `http://localhost:8001/admin/` |

---

## Lancement rapide

```bash
# Backend
cd backend
source venv/bin/activate
python manage.py runserver 0.0.0.0:8001

# Frontend (autre terminal)
cd frontend
npm run dev
```
