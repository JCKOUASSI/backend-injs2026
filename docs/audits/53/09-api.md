# Livrable 9 — API du module Référentiels

Toutes les routes sont montées sous `/api/referentiels/`. Lecture ouverte à tout
utilisateur authentifié (règle 9 : aucune valeur métier codée en dur côté
React/Flutter) ; écriture réservée aux rôles administratifs.

## 9.1 Routes du registre (une seule source)

| Méthode | Route | Rôle |
|---|---|---|
| `GET` | `/api/referentiels/tableau-de-bord/` | Cartographie complète : catégories, entrées, volumétrie, traçabilité |
| `GET` | `/api/referentiels/journal/` | Journal des modifications (lecture seule) |

## 9.2 Référentiels métier de la refonte (CRUD générique)

Un `ViewSet` unique sert les six référentiels créés par la mission ; le slug du
registre choisit le modèle. Le contrat est identique partout :

| Méthode | Route | Rôle |
|---|---|---|
| `GET` | `/api/referentiels/{slug}/` | Liste paginée (`?actif=`, `?archives=1`, `?page_size=`) |
| `POST` | `/api/referentiels/{slug}/` | Création (code + libellé obligatoires, code immuable ensuite) |
| `GET` | `/api/referentiels/{slug}/{id}/` | Détail |
| `PATCH` | `/api/referentiels/{slug}/{id}/` | Modification partielle |
| `POST` | `/api/referentiels/{slug}/{id}/archiver/` | Archivage réversible (aucune suppression physique) |
| `POST` | `/api/referentiels/{slug}/{id}/reactiver/` | Réactivation — remet aussi la valeur en service |

Slugs servis : `ecoles`, `mentions`, `filieres`, `types-cursus`,
`statuts-vague`, `types-enseignement`.

## 9.3 Référentiels historiques (ViewSets dédiés)

| Route | Modèle |
|---|---|
| `/api/referentiels/types-evaluation/` | `RefTypeEvaluation` |
| `/api/referentiels/types-document/` | `RefTypeDocument` |
| `/api/referentiels/grades-enseignant/` | `RefGradeEnseignant` |
| `/api/referentiels/types-frais/` | `RefTypeFrais` |
| `/api/referentiels/modes-paiement/` | `RefModePaiement` |
| `/api/referentiels/types-decision/` | `RefTypeDecision` |
| `/api/referentiels/types-notification/` | `RefTypeNotification` |
| `/api/referentiels/types-espace-sportif/` | `RefTypeEspaceSportif` |

Ces huit routes partagent exactement le même contrat que §9.2 (mêmes actions
`archiver`/`reactiver`, même sérialiseur de socle, donc les mêmes champs de
traçabilité).

## 9.4 Données importées, en lecture seule

| Route | Contenu | Pagination |
|---|---|---|
| `/api/referentiels/modules-officiels/` | 227 modules des maquettes | 100 / page, `page_size` jusqu'à 1000 |
| `/api/referentiels/volumes-horaires/` | 51 répartitions CM/TD/TP/stage | idem |

Ces deux routes sont servies par des `ReadOnlyModelViewSet` : aucune écriture
n'est exposée, car les données viennent d'un document et ne peuvent être
corrigées que par un nouvel import.

## 9.5 Routes des référentiels hébergés par d'autres modules

Le tableau de bord les référence sans les dupliquer :

| Registre | Route réelle | Module propriétaire |
|---|---|---|
| Formations (cycles) | `/api/formations/ref/formations/` | `formations` |
| Sites / bâtiments / salles / vagues | `/api/formations/ref/{sites,batiments,salles,vagues}/` | `formations` |
| Niveaux / semestres / parcours / années | `/api/scolarite/ref/{niveaux,semestres,parcours,annees}/` | `scolarite` |
| Modules, catégories, grades | `/api/formations/ref/...` | `formations` |

## 9.6 Contrat de réponse (socle)

```json
{
  "id": 1,
  "code": "ENSEPS",
  "libelle": "École Normale Supérieure d'Éducation Physique et Sportive",
  "description": "",
  "actif": true,
  "date_activation": null,
  "date_desactivation": null,
  "archive": false,
  "annee_academique": null,
  "source_document": "Formations et Modules INJS — §1",
  "fiabilite": "OFFICIEL",
  "cree_le": "2026-10-31T21:12:04+0000",
  "modifie_le": "2026-10-31T21:12:04+0000"
}
```

Champs métier supplémentaires selon le référentiel (`nom_complet`, `abrege`,
`est_stage`, `est_ouvert`…) et libellés des clés étrangères
(`ecole_libelle`, `mention_libelle`, `type_cursus_libelle`) pour que le front
n'ait jamais à recoder une liste.

## 9.7 Erreurs normalisées

| Cas | Statut | Corps |
|---|---|---|
| Code hors format (`A-Z 0-9 _`, 2 à 50) | `400` | `{"code": ["Code invalide : …"]}` |
| Libellé vide | `400` | `{"libelle": ["Le libellé est obligatoire."]}` |
| Doublon de code ou de libellé (insensible à la casse) | `400` | `{"detail": "Cette valeur existe déjà (code ou libellé en doublon)."}` |
| `DELETE` | `405` | Méthode non exposée : l'archivage est la seule sortie |
| Archivage d'une valeur déjà archivée | `400` | `{"detail": "Valeur déjà archivée."}` |
| Réactivation d'une valeur active | `400` | `{"detail": "Valeur non archivée."}` |
| Rôle sans droit d'écriture | `403` | Contrôlé par `ReferentielPermission` |

## 9.8 Vérifications exécutées

| Contrôle | Résultat |
|---|---|
| `test_route_api_declaree_existe_vraiment` | Chaque `route_api` du registre répond (pas de `404`) |
| Requêtes réelles sur les 11 routes (jeton admin) | `200` / pagination conforme |
| Création, modification, archivage, réactivation via HTTP | `201`, `200`, `200`, `200` |
| `DELETE` | `405`, valeur toujours présente en base |
