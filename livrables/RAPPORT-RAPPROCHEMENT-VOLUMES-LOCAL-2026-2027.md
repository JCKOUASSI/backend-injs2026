# Rapprochement des volumes CM/TD/TP — 2026‑2027

**Portée : base SQLite locale du dépôt, pas la base du site public.** Exécution en lecture seule. Ce rapport ne prouve rien sur les maquettes actuellement servies par `injs.badge-qr-code.pro` ; le même audit doit être exécuté contre le backend de production avant toute décision de reprise ou d'importation.

## Constat local

- 8 années académiques parcourues ; 16 formations, toutes les filières représentées dans les 40 maquettes consultées ; 40 maquettes `ACTIVE`, dont 16 pour 2026‑2027.
- 779 ECUE inspectées dans toutes les années ; **aucune n'a de volume CM, TD ou TP positif** dans cette base. Les 779 ECUE de l'année cible sont toutes sans source ECUE vérifiable. La liste exacte (formation, filière, niveau, semestre, UE, ECUE, maquette et volumes actuels) est dans `audit-volumes-LOCAL-2026-2027.csv` ; le détail des références et des correspondances est dans `audit-volumes-LOCAL-2026-2027.json`.
- Un autre référentiel contient 51 lignes « volume horaire de module / formation », dont 47 avec au moins un volume positif. **Les 51 portent `fiabilite=MODELISE`, source « Modéliser les volumes horaires (proposition) » ; aucune n'a pu être rattachée par identité exacte de titre de module à l'ECUE d'une même formation** dans l'année cible. Un module (sans niveau/semestre/UE attesté) n'est pas une ECUE ; ces valeurs ne sont ni institutionnelles ni transférables automatiquement.
- Le référentiel opérationnel des modules et celui « module × formation × catégorie » ne portent ici aucun total positif. Un total de module ne permettrait de toute façon pas de ventiler CM/TD/TP.

### ECUE manquantes par formation (année cible, base locale)

| Formation | ECUE sans volume |
|---|---:|
| Éducation et motricité — Licence | 73 |
| Activités physiques adaptées — Licence | 76 |
| Entraînement sportif — Licence | 73 |
| Management du sport — Licence | 77 |
| Éducation et motricité — Master | 27 |
| Activités physiques adaptées — Master | 28 |
| Entraînement sportif — Master | 26 |
| Management du sport — Master | 27 |
| Andragogie — Licence / Master | 63 / 30 |
| Loisir — Licence / Master | 63 / 30 |
| Entrepreneuriat jeunesse et conduite de projets — Licence / Master | 63 / 30 |
| Gérontologie — Licence / Master | 63 / 30 |
| **Total** | **779** |

## Règles de rapprochement et suite

Une correspondance ECUE exacte exige la même formation, le même parcours, le même niveau, le même numéro de semestre, le même code d'UE et le même code d'ECUE. Une valeur positive sur une autre maquette est **candidate à validation**, non une valeur institutionnelle par défaut (les ECUE n'historisent pas la provenance du volume). Plusieurs triplets CM/TD/TP pour cette clé sont marqués **contradictoires**. Une ligne du référentiel de modules est seulement indicative, même quand son intitulé coïncide. Le rapport ne change **aucune** maquette, ECUE, campagne ni EDT.

1. Exécuter l'audit contre la base de production réellement utilisée ; comparer les inventaires et les identifiants. Ne pas utiliser ce rapport local pour modifier la production.
2. Si la production contient des valeurs positives vérifiables : faire approuver explicitement les clés et documents source, puis préparer des **nouvelles versions brouillon** des maquettes concernées. Les maquettes `ACTIVE` sont immuables ; conserver et ne pas écraser les anciennes.
3. Si la production présente aussi les volumes absents, demander les heures CM/TD/TP institutionnelles pour chacune des ECUE listées. Le calendrier provisoire autorisé ne donne **aucune** autorisation d'inventer ces heures.
4. Ce préalable ne prouve pas qu'une génération annuelle complète aboutira : vérifier ensuite créneaux, salles, enseignants, semestre et bilan, sans publier automatiquement les EDT.
