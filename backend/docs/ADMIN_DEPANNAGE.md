# Guide de dépannage — Admin Django INJS-LMD

Ce document décrit les procédures pour diagnostiquer et corriger les problèmes courants de l’interface d’administration (`/admin/`).

**Public :** administrateurs techniques, encadrants avec accès staff, équipe support.

**URL admin :** `https://<domaine>/admin/` (en local : `http://localhost:8001/admin/`)

---

## 1. Vérifications rapides (à faire en premier)

### 1.1 L’admin ne répond pas ou erreur 500

1. Vérifier que le serveur Django tourne :
   ```bash
   cd backend
   source venv/bin/activate   # si besoin
   python manage.py runserver 0.0.0.0:8001
   ```
2. Lancer les contrôles Django :
   ```bash
   python manage.py check
   ```
3. Consulter les logs du terminal ou du serveur (Gunicorn / Render) au moment de l’erreur.
4. Noter l’URL exacte, l’heure, le compte utilisé et copier le message d’erreur affiché.

### 1.2 Page blanche (écran vide)

**Causes fréquentes :**
- Erreur de template Django (souvent visible dans les logs serveur)
- Fichier CSS qui masque tout le contenu (`#container` caché)
- Cache navigateur obsolète

**Procédure :**
1. Ouvrir les outils développeur du navigateur (F12) → onglet **Console** : noter les erreurs JavaScript.
2. Onglet **Réseau** : vérifier que `/static/admin/custom_admin.css` répond en **200** ou **304**.
3. Forcer le rechargement : **Ctrl+Shift+R** (Windows/Linux) ou **Cmd+Shift+R** (Mac).
4. Tester en navigation privée.
5. Si la page reste blanche, lire la trace dans le terminal Django (erreur `TemplateSyntaxError`, etc.).

### 1.3 Styles cassés (admin « moche » ou sans sidebar)

**Cause :** les fichiers statiques ne sont pas servis ou le mauvais template est utilisé.

**Procédure :**
1. Vérifier que la page charge bien :
   - `/static/admin/custom_admin.css`
   - `/static/admin/login.css` (page de connexion)
   - `/static/admin/changelist_filters.js` (listes avec filtres)
2. En production, regénérer les statiques :
   ```bash
   cd backend
   python manage.py collectstatic --noinput
   ```
3. Redémarrer le serveur après `collectstatic`.
4. Vérifier que les templates admin étendent **`admin/base_site.html`** (et non `admin/base.html` seul) pour les pages personnalisées.

---

## 2. Connexion et déconnexion

### 2.1 Impossible de se connecter

1. Vérifier identifiant / mot de passe.
2. Vérifier que le compte est **actif** et **staff** (`is_staff = True`) dans la table utilisateurs.
3. Réinitialiser le mot de passe (superutilisateur) :
   ```bash
   python manage.py changepassword <username>
   ```
4. Créer un superutilisateur si nécessaire :
   ```bash
   python manage.py createsuperuser
   ```

### 2.2 Page blanche après déconnexion

**Comportement attendu :** redirection vers `/admin/login/` avec le formulaire de connexion stylisé.

**Si page blanche :**
1. Vérifier que `backend/config/admin_site.py` contient bien `custom_logout` avec redirection vers la page login.
2. Vérifier dans `custom_admin.css` que **`#container` n’est pas masqué globalement** (seuls `#header` et `.breadcrumbs` peuvent l’être).
3. Vider le cache navigateur et réessayer.

### 2.3 Boucle de redirection (302 en boucle)

1. Vérifier `ALLOWED_HOSTS` et `CSRF_TRUSTED_ORIGINS` dans `.env` / `settings.py`.
2. S’assurer que l’URL utilisée correspond au domaine configuré.
3. En production derrière un proxy, vérifier `SECURE_PROXY_SSL_HEADER` si HTTPS.

---

## 3. Interface — sidebar, accueil, filtres

### 3.1 Sidebar : sections ne se replient pas

**Fichiers concernés :**
- `backend/templates/admin/includes/sidebar.html`
- `backend/dashboard/templatetags/admin_ui_tags.py`
- `backend/static/admin/custom_admin.css`

**Procédure :**
1. Recharger la page avec cache vidé.
2. Vérifier que les icônes Material Symbols se chargent (connexion Google Fonts dans `base_site.html`).
3. Une section s’ouvre automatiquement si la page active appartient à cette section.

### 3.2 Accueil admin affiché bizarrement

**Fichiers concernés :**
- `backend/templates/admin/index.html` → doit étendre `admin/base_site.html`
- `backend/config/admin_dashboard.py` → statistiques du tableau de bord
- `backend/config/admin_site.py` → vue d’accueil personnalisée

**Procédure :**
1. Confirmer que `index.html` contient `{% extends "admin/base_site.html" %}`.
2. Vérifier que `custom_admin.css` est chargé.
3. Exécuter `python manage.py check`.

### 3.3 Bouton « Filtres » ne s’ouvre pas (listes admin)

**Fichiers concernés :**
- `backend/templates/admin/change_list.html`
- `backend/static/admin/changelist_filters.js`
- `backend/static/admin/custom_admin.css`

**Procédure :**
1. Ouvrir une liste avec filtres (ex. Pointages, Utilisateurs).
2. Vérifier dans l’onglet Réseau que `changelist_filters.js` est chargé (statut 200).
3. Console JavaScript : erreurs éventuelles.
4. Le panneau filtres s’ouvre à droite ; fermeture via **X**, clic extérieur ou **Échap**.

### 3.4 Erreur template : `block 'messages' appears more than once`

**Cause :** un bloc Django (`messages`, `content`, `coltype`) est défini deux fois dans `base.html`.

**Procédure :**
1. Ouvrir `backend/templates/admin/base.html`.
2. S’assurer que chaque `{% block %}` n’existe **qu’une seule fois** dans le fichier (pas de duplication dans des branches `if/else`).
3. Redémarrer le serveur et recharger `/admin/`.

---

## 4. Permissions et accès aux données

### 4.1 « Vous n’avez pas la permission » / liste vide

L’admin applique un **filtrage par rôle** via `backend/admin_mixins.py` (`AdminScopeMixin`).

| Rôle | Portée typique |
|------|----------------|
| ADMIN, INJS_ADMIN, DIRECTION, FINANCE | Accès global |
| SECRETARIAT, CHEF_SECRETARIAT | Données de leur secrétariat |
| ENCADRANT | Modules / séances supervisés |

**Procédure :**
1. Vérifier le **groupe Django** (`ROLE_*`) de l’utilisateur dans Admin → Utilisateurs.
2. Un seul groupe de rôle par utilisateur est recommandé.
3. Vérifier le secrétariat lié au compte si rôle secrétariat.
4. Pour un encadrant, vérifier l’affectation comme superviseur sur les modules concernés.

### 4.2 Action admin refusée (pointage, rattrapage, etc.)

1. Lire le message affiché en haut de page (bandeau jaune/rouge).
2. Consulter **Journal d’audit** (`presences → Journal d'audit`) pour l’historique des actions.
3. Vérifier le statut métier de l’objet (ex. pointage déjà en cours, rattrapage annulé).

---

## 5. Opérations métier courantes dans l’admin

### 5.1 Remettre un pointage « en cours »

1. Aller dans **Présences → Pointages**.
2. Cliquer **Remettre en cours** sur la ligne, ou ouvrir la fiche → bouton dédié.
3. Confirmer la boîte de dialogue.
4. L’action est tracée dans le journal d’audit.

### 5.2 Créer / gérer un rattrapage

1. **Présences → Rattrapages** (ou flux badgeage selon écran).
2. Renseigner auditeur, séance de rattrapage (autre cohorte).
3. Action groupée : **Générer / forcer la présence**.
4. En cas d’erreur, lire le message par ligne dans le bandeau admin.

### 5.3 Diagnostic volume horaire

1. Sidebar → **Diagnostic volume horaire** (`/admin/diagnostique-volume-horaire/`).
2. Cocher « dépassements seulement » si besoin.
3. Comparer **Prévu** (créneaux planifiés) et **Réalisé** (séances terminées).

### 5.4 Gérer les utilisateurs et rôles

1. **Administration → Utilisateurs**.
2. Attribuer **un seul** groupe `ROLE_*` (détermine permissions et rôle affiché).
3. Ne pas modifier `is_superuser` sans validation de l’équipe technique.

---

## 6. Base de données et migrations

### 6.1 Erreur au démarrage liée aux migrations

```bash
cd backend
python manage.py showmigrations
python manage.py migrate
```

Si une migration échoue :
1. Copier le message d’erreur complet.
2. Ne pas supprimer de migrations sans accord technique.
3. En dernier recours (développement local uniquement) :
   ```bash
   python manage.py migrate <app> <migration_précédente>
   python manage.py migrate
   ```

### 6.2 Données incohérentes après import

1. Vérifier les imports Excel via les écrans prévus (formations, participants).
2. Utiliser le **journal d’audit** pour identifier les dernières modifications.
3. Commandes de réparation éventuelles dans `backend/authentication/management/commands/` et `backend/presences/management/commands/` (à lancer uniquement si documentées par l’équipe dev).

---

## 7. Production (Render / serveur)

### 7.1 Checklist après déploiement

- [ ] `python manage.py migrate` exécuté
- [ ] `python manage.py collectstatic` exécuté
- [ ] Variables d’environnement : `SECRET_KEY`, `POSTGRES_*`, `PUBLIC_APP_URL`, `DJANGO_ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`
- [ ] `DEBUG=False` en production
- [ ] Redémarrage du service après déploiement

### 7.2 Admin lent

1. Réduire les filtres actifs sur les grosses listes (Pointages).
2. Utiliser la recherche plutôt que d’afficher toute la table.
3. Vérifier la charge serveur / base PostgreSQL.

---

## 8. Fichiers clés de l’interface admin (référence technique)

| Fichier | Rôle |
|---------|------|
| `backend/config/admin_site.py` | Config admin, accueil, déconnexion |
| `backend/config/admin_sidebar.py` | Liens de la sidebar |
| `backend/config/admin_dashboard.py` | Statistiques page d’accueil |
| `backend/config/context_processors.py` | Injection sidebar dans les templates |
| `backend/templates/admin/base.html` | Layout principal (sidebar + topbar) |
| `backend/templates/admin/base_site.html` | CSS, polices, branding |
| `backend/templates/admin/index.html` | Tableau de bord accueil |
| `backend/templates/admin/change_list.html` | Listes + bouton Filtres |
| `backend/templates/admin/login.html` | Page de connexion |
| `backend/static/admin/custom_admin.css` | Thème visuel |
| `backend/static/admin/login.css` | Styles connexion |
| `backend/static/admin/changelist_filters.js` | Panneau filtres |
| `backend/admin_mixins.py` | Permissions / périmètre par rôle |

---

## 9. Escalade vers l’équipe développement

Préparer un ticket avec :

1. **URL exacte** (ex. `/admin/presences/pointage/`)
2. **Compte utilisateur** (rôle, secrétariat)
3. **Capture d’écran** ou description visuelle
4. **Message d’erreur** (écran + log serveur)
5. **Heure** de l’incident
6. **Actions déjà tentées** (rechargement, autre navigateur, etc.)

Commandes utiles à joindre au ticket :

```bash
python manage.py check
python manage.py showmigrations
# Extrait des logs serveur autour de l’heure de l’erreur
```

---

## 10. Procédures de secours

### 10.1 Accès admin totalement bloqué

1. Se connecter au serveur / conteneur.
2. Créer ou réinitialiser un superutilisateur :
   ```bash
   cd backend
   python manage.py createsuperuser
   ```
3. Se connecter avec ce compte et corriger les comptes utilisateurs.

### 10.2 Revenir à l’admin Django « par défaut » (urgence extrême)

> À n’utiliser que si l’interface personnalisée empêche toute utilisation.

1. Renommer temporairement `backend/templates/admin/base.html` (ex. `base.html.bak`).
2. Redémarrer Django : l’admin utilisera le template Django d’origine.
3. Remettre le fichier dès que le correctif est appliqué.

### 10.3 Restaurer les styles après modification CSS

1. Vérifier le fichier `backend/static/admin/custom_admin.css`.
2. En production : `python manage.py collectstatic --noinput` puis redémarrage.
3. Vider le cache CDN / navigateur si applicable.

---

*Dernière mise à jour : juillet 2026 — interface admin personnalisée (sans django-unfold).*
