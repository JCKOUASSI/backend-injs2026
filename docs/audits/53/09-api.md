# Livrable 9 — API créées et modifiées

Toutes les routes sont sous `/api/referentiels/`. L'authentification est celle du projet (JWT) ; les permissions sont celles de `referentiels.ReferentielPermission` : lecture pour tout compte authentifié, écriture réservée aux rôles de gestion.

## 9.1 API créées

| Méthode | Route | Rôle | Permission | Remarque |
|---|---|---|---|---|
| `GET` | `/tableau-de-bord/` | Cartographie complète : 7 catégories, 26 référentiels, compteurs, synthèse et taux de traçabilité | authentifié | Construite **entièrement** depuis le registre, aucune liste en dur |
| `GET` | `/<slug>/` | Liste paginée d'un référentiel éditable | authentifié | `?archives=1` pour voir les valeurs archivées, `?actif=true|false` |
| `POST` | `/<slug>/` | Création | rôles de gestion | Contrôle anti-doublon normalisé (casse/accents) + contrainte base |
| `GET` | `/<slug>/<pk>/` | Détail | authentifié | Inclut les libellés des clés étrangères (`ecole_libelle`, `mention_libelle`…) |
| `PATCH` / `PUT` | `/<slug>/<pk>/` | Modification | rôles de gestion | `code` immuable ; diff journalisé |
| `POST` | `/<slug>/<pk>/archiver/` | Archivage réversible | rôles de gestion | `400` si déjà archivé ; accepte un `motif` |
| `POST` | `/<slug>/<pk>/reactiver/` | Réactivation | rôles de gestion | `400` si non archivé |
| `GET` | `/modules-officiels/` | Lecture seule des 227 modules | authentifié | Filtres `?filiere=`, `?semestre=`, `?formation=` ; écriture impossible (`405`) |
| `GET` | `/volumes-horaires/` | Lecture seule des 51 volumes horaires | authentifié | Idem |
| `DELETE` | *aucune* | — | — | Volontairement non exposé : archivage uniquement |

**Slugs éditables (14)** : `ecoles`, `mentions`, `types-cursus`, `filieres`, `types-enseignement`, `statuts-vague`, `types-evaluation`, `types-decision`, `types-espace-sportif`, `grades-enseignant`, `types-document`, `types-frais`, `modes-paiement`, `types-notification`.

## 9.2 API conservées sans changement de contrat

| Route | Consommateur | Statut |
|---|---|---|
| `/referentiels/types-evaluation/`, `types-document/`, `grades-enseignant/`, `types-frais/`, `modes-paiement/`, `types-decision/`, `types-notification/`, `types-espace-sportif/` | Frontend (écrans génériques), mobile | **Inchangées** : leurs ViewSets dédiés restent prioritaires ; le registre les déclare avec `route_api` explicite pour qu'aucune route générique ne les masque |
| `/scolarite/ref/{niveaux,semestres,parcours,annees,types-formation}/` | Scolarité, maquettes | Inchangées |
| `/formations/ref/{formations,sites,batiments,salles,vagues,modules}/` | Formations, EDT | Inchangées, enrichies de `filiere`, `fiabilite`, `source_document` |

## 9.3 Correctifs d'API apportés pendant la mission

| Défaut constaté | Correction |
|---|---|
| Les routes génériques `/<slug>/…` étaient construites avec `as_view({...})` **sans** le slug : tout accès répondait `404 Référentiel inconnu` | Le slug est transmis à `as_view(..., slug=slug)` ; vérifié par requêtes réelles (`200` sur les 6 slugs concernés) |
| Les actions `archiver`/`reactiver` étaient mappées sur une méthode HTTP inexistante (`405`) | Mapping corrigé en `{'post': _action}` |
| Les 8 référentiels du socle recevaient une **seconde** route générique qui écrasait leur ViewSet dédié (régression des tests d'archivage) | Les entrées déclarant `route_api` sont exclues de la génération générique |
| `_routes_selecteurs()` supposait `modele` objet alors que certaines entrées déclarent une chaîne (`'formations.RefSalle'`) → `500` sur le tableau de bord | Résolution via `modele_de()` |
| Pagination DRF globale à 50 lignes : les listes (227 modules) étaient tronquées sans le dire | `RefPagination` (`page_size=100` par défaut, `max 1000`) sur les ViewSets du module |
| Réponse `{count, results}` non gérée par le front | Normalisation côté client (`listeRecue`) |

## 9.4 Exemples de réponses

`GET /api/referentiels/tableau-de-bord/` (extrait) :

```json
{
  "synthese": {
    "nb_referentiels": 26,
    "nb_referentiels_editables": 14,
    "nb_valeurs": 546,
    "nb_a_renseigner": 20,
    "nb_sans_source": 20,
    "nb_valeurs_tracees": 507,
    "taux_tracabilite": 0.9606
  },
  "categories": [
    {
      "cle": "offre-formation",
      "libelle": "Offre de formation",
      "entrees": [
        {
          "slug": "filieres",
          "libelle": "Filières",
          "editable": true,
          "total": 8,
          "a_renseigner": 0,
          "route_api": "/referentiels/filieres/",
          "selecteurs_routes": {
            "ecole":        {"slug": "ecoles",       "route": "/referentiels/ecoles/",       "editable": true},
            "mention":      {"slug": "mentions",     "route": "/referentiels/mentions/",     "editable": true},
            "type_cursus":  {"slug": "types-cursus", "route": "/referentiels/types-cursus/", "editable": true}
          }
        }
      ]
    }
  ]
}
```

`GET /api/referentiels/filieres/?page_size=1000` (extrait) :

```json
{"code": "EM", "libelle": "Éducation et Motricité", "code_dossier": "F01",
 "ecole_libelle": "ENSEPS", "mention_libelle": "STAPS",
 "type_cursus_libelle": "Cursus LMD (Licence-Master)",
 "fiabilite": "OFFICIEL", "source_document": "Formations et Modules INJS — §1"}
```
