# Livrable 8 — Volumes importés par référentiel

Exécution réelle de `python manage.py importer_referentiels_injs` (base de développement, SQLite). Les comptes ci-dessous sont **mesurés**, non estimés.

## 8.1 Bloc 1 — Institutions

| Référentiel | Créés | Mis à jour (2ᵉ passage) | Total en base | Fiabilité |
|---|---|---|---|---|
| Écoles | 2 | 2 | **2** | OFFICIEL |
| Mentions | 2 | 2 | **2** | OFFICIEL |
| Natures de cursus | 5 | 5 | **5** | OFFICIEL (LMD) / CADRAGE (4) |
| Filières | 8 | 8 | **8** | OFFICIEL |
| Statuts de vague | 5 | 5 | **5** | OFFICIEL |
| Types d'enseignement | 4 | 4 | **4** | OFFICIEL |

## 8.2 Bloc 2 — Cycles LMD

| Filière | Licence | Master |
|---|---|---|
| F01 Éducation et Motricité | déjà présent | déjà présent |
| F02 Activités Physiques Adaptées | déjà présent | déjà présent |
| F03 Entraînement Sportif | déjà présent | déjà présent |
| F04 Management du Sport | déjà présent | déjà présent |
| F05–F08 | *aucun cycle LMD documenté* | *aucun cycle créé* |

**0 cycle créé au 2ᵉ passage** (les 8 cycles existaient déjà) — l'étape est idempotente et ne modifie jamais un cycle existant.

## 8.3 Bloc 3 — Modules officiels (227)

| Filière | Licence | Master | Total |
|---|---:|---:|---:|
| EM — Éducation et Motricité | 58 | 23 | **81** |
| ES — Entraînement Sportif | 41 | 12 | **53** |
| MS — Management du Sport | 22 | 11 | **33** |
| APA — Activités Physiques Adaptées | 43 | 17 | **60** |
| **Total** | **164** | **63** | **227** |

## 8.4 Bloc 4 — Bâtiments et espaces

| Référentiel | Total | Fiabilité |
|---|---:|---|
| Site (INJS Marcory) | **1** | OFFICIEL |
| Bâtiments | **16** | MODELISE |
| Espaces (salles) | **166** | MODELISE |

Les 19 bâtiments et 173 salles présents en base incluent 3 bâtiments et 7 salles créés antérieurement, hors import documentaire (écart tracé par l'anomalie **A-53-05**).

## 8.5 Bloc 5 — Volumes horaires (51)

| Cursus | Modules | Fiabilité |
|---|---:|---|
| EM Licence | 16 | MODELISE |
| EM Master | 12 | MODELISE |
| APA Licence | 12 | MODELISE |
| APA Master | 11 | MODELISE |
| **Total** | **51** | MODELISE |

**Exclu et tracé** : « 8. Maître(sse) d'Éducation Physique et Sportive » (14 modules) — corpus CPFAE, hors périmètre INJS.

## 8.6 Preuve d'idempotence

| Exécution | Résultat |
|---|---|
| 1ʳᵉ | Créations réelles (comptes ci-dessus) |
| 2ᵉ | `0 créé(s), 2 mis à jour` (écoles) · `0 créé(s), 227 mis à jour` (modules) · `0 créé(s), 166 mis à jour` (espaces) · `0 créé(s), 51 mis à jour` (volumes) · `0 cycle(s) créé(s)` |
| 3ᵉ (après correctifs) | Identique : aucun doublon, aucun cycle recréé |

## 8.7 Livrable de contrôle

`python manage.py verifier_coherence_referentiels` sur la base courante :

```
A-53-01  1 occurrence   (doublon sémantique Formation continue)
A-53-03  1 occurrence   (cycle hérité sans filière : « Licence STAPS … »)
A-53-05  20 occurrences (valeurs sans source documentaire : typologies d'espace,
                         sites/bâtiments/salles hérités, vagues héritées)
Total : 22 anomalies sur 3 familles.
```

Aucune n'a été corrigée automatiquement : chacune exige une décision (voir livrable 13).
