# GET INJS APP — algorithme actuellement déployé

**Référence technique :** commit `70d08dad1821caceb61b22fe22cf70e13155bf18` (backend et frontend de la candidate ensuite servie par `injs.badge-qr-code.pro`). Ce document décrit le **code déployé**, pas les correctifs non déployés dans l’espace de travail. Sources Python/JS exactes dans `GET-INJS-SOURCES-70d08da.zip`. État métier observé lors du déploiement : l’année `2026-2027` a été requalifiée **provisoirement, non officiellement**, du `01/10/2026` au `30/09/2027` (53 semaines ; bascule estimée le `01/04/2027`). Cette donnée de production n’est pas une constante du code.

## 1. Périmètre et entrées

L’application importe des inscrits, prépare des **besoins d’enseignement**, cherche des créneaux et des salles, valide des placements, enregistre éventuellement des EDT **BROUILLON**, puis offre un circuit distinct de validation/publication. Entrées : année académique ; formations INJS, niveaux, groupes et semestres ; inscrits et effectifs ; affectations pédagogiques ou maquettes **ACTIVE** (UE → ECUE → volumes CM/TD/TP) ; canevas de créneaux ; salles, capacités et disponibilités ; occupations existantes ; politique de contraintes ; options de périmètre, samedi et pause.

Import CSV/XLSX : correspondance et validation de colonnes, résolution précise formation/cycle/filière, niveau, semestre, parcours, groupe et vague. `appliquer=False` analyse sans écrire ; `appliquer=True` écrit en transaction avec clé `(année, matricule)` et rapport de lignes rejetées. Les groupes importés sans affectation d’enseignant sont pris en charge par la maquette. L’import **n’invente pas** de volumes horaires.

## 2. Deux modes de génération

- **Manuel :** périmètre choisi à l’écran ; prévisualisation préalable du périmètre exact ; semaines saisies prises en compte. Un ciblage multi-semaines n’est distribué en occurrences unitaires que dans les conditions de semestre explicitement ciblé ; sinon le moteur refuse de traiter un bloc récurrent comme une année complète si les occurrences/heures réelles ne correspondent pas aux besoins.
- **Automatique « toute l’année » :** ignore les cases de périmètre et le champ « semaines planifiées » du mode manuel. Demande une **confirmation explicite** des dates et du découpage **provisoire non officiel** ; le backend recalcule les semaines depuis `AnneeAcademique.date_debut/date_fin`, vérifie les dates confirmées, impose tout le périmètre, désactive la publication directe et ignore le quota manuel. Il refuse une année de moins de 4 ou plus de 53 semaines. À l’exécution, si les dates ont changé depuis la confirmation, la campagne est refusée.

Pour une durée inclusive de `N` jours, `W = plafond(N / 7)` ; semaines impaires = `1..plancher(W/2)`, semaines paires = la suite jusqu’à `W`. Les besoins de semestres **impairs** (S1, S3…) vont dans la première plage, ceux des semestres **pairs** (S2, S4…) dans la seconde. Le nom « impairs/pairs » désigne ici la parité du **semestre**, non celle du numéro de semaine. Semestre absent/inconnu : **non placé**, jamais attribué arbitrairement. Cette division uniforme n’est **pas** le calendrier institutionnel S1/S2.

## 3. Déroulement réel (pseudo-code)

```text
Créer campagne BROUILLON (année, paramètres, périmètre)
  si automatique : exiger confirmation et dates inchangées ; proposer W semaines ;
                    forcer périmètre complet et publier_direct = faux
Marquer données prêtes ; démarrer l'exécution asynchrone avec verrou de campagne
  sélectionner les groupes actifs des formations INJS pour l'année
  calculer les effectifs réels des inscrits importés
  par groupe :
    utiliser d'abord les besoins des affectations pédagogiques existantes
    si aucune affectation et option maquette activée :
      choisir maquette ACTIVE (parcours spécifique avant formation générale,
      version la plus récente), puis créer un besoin pour chaque CM/TD/TP > 0
    si aucun besoin : motif explicite (sans maquette, sans volume, etc.)
    retirer les créneaux du samedi/pause si options choisies
    si calendrier automatique provisoire : séparer les besoins par parité
      du semestre et répartir les séances en semaines unitaires de sa plage
    chercher des placements compatibles sans conflit entre groupes
    contrôler séances, heures, récurrence, couverture et violations
    si persistance autorisée et plan suffisamment valide : transaction
      par EDT BROUILLON ; remplacer les séances générées du périmètre ciblé
  produire bilan groupes + totaux + anomalies + statut global
Validation de campagne distincte : exiger COMPLETE et sans anomalies,
  revérifier les EDT persistés ; publication distincte, atomique et habilitée
```

## 4. Calcul des besoins et choix des ressources

Les affectations pédagogiques sont prioritaires. Pour les cohortes restantes, les volumes **strictement positifs** des ECUE de la maquette ACTIVE deviennent des `TeachingNeed` distincts (CM, TD, TP) ; un type à zéro est ignoré. La durée provient du canevas réel ; `nb_seances = max(1, round(volume / duree_seance))`. Sans canevas, maquette ACTIVE ou volume exploitable : refus documenté. L’enseignant d’une cohorte issue de la seule maquette reste **non affecté** (`None`) ; le moteur ne peut alors garantir sa disponibilité ou l’absence de ses conflits. L’effectif provient des inscrits importés quand disponible, avec repli sur la capacité du groupe.

Le solveur trie les besoins par difficulté et génère des couples **créneau/salle**. Il écarte les indisponibilités et conflits d’enseignant, groupe ou salle ; vérifie type de salle et capacité ; classe les candidats par score de pénalités puis jour/heure/salle. Les salles compatibles les plus ajustées à l’effectif sont examinées d’abord. La recherche par retour arrière est **déterministe**, bornée par un budget par défaut de `200 000` essais de placement. En cas d’impasse, elle conserve la meilleure branche puis tente une complétion gloutonne dans le budget restant. Les occupations déjà persistées et les placements des groupes précédents participent aux conflits. Les règles souples (trous, longues séries, journées chargées) sont **désactivées par défaut** ; elles influencent le score lorsqu’activées, jamais les contraintes dures.

Contraintes dures repérées dans le code : `C1` conflit enseignant ; `C2` groupe ; `C3` salle ; `C4` capacité ; `C5` disponibilité enseignant ; `C6` disponibilité salle ; `C7` compatibilité salle ; `C8` cohérence pédagogique ; `C9` calendrier ; `C10` volume/couverture. Une séance sans enseignant identifié reste un point à compléter avant exploitation institutionnelle.

## 5. Persistance, bilan et limites importantes

Le solveur seul **n’écrit pas** en base. La campagne peut persister des séances après validation ; la réexécution avec `remplacer=true` remplace les séances générées de son périmètre, pas toute la base. La persistance est par EDT ; en automatique provisoire, un groupe incomplet n’est pas persisté comme s’il était complet. Les bilans distinguent `COMPLETE`, `PARTIELLE`, `IMPOSSIBLE`, séances attendues/placées/non placées, heures, couverture, anomalies et motifs. Une campagne ne peut être validée que si le bilan est complet **et** sans anomalies ; la publication suit une action distincte, atomique, jamais automatique dans le mode annuel provisoire.

**Attention — état réel du commit déployé :** la source maquette saute les CM/TD/TP à zéro et signale `VOLUMES_HORAIRES_ABSENTS` quand un groupe n’a **aucun besoin volumée**. Elle ne prouve **pas** que chaque ECUE d’une maquette partiellement volumée possède tous ses types applicables ni que chaque heure positive est attestée institutionnellement. Le contrôle renforcé par ECUE, provenance et types applicables développé localement après ce commit **n’est pas déployé**. Ne pas interpréter un statut `COMPLETE` technique comme une attestation officielle de tous les volumes. Aucun des 779 triplets d’heures modélisées localement n’a été validé ni importé comme volume institutionnel.

La proposition de 53 semaines déduite de l’année en production est **un cadrage provisoire**, non une preuve des semaines officielles. Même si l’interface propose désormais la confirmation, lancer une génération globale avec `remplacer=true` touche les séances existantes du périmètre : prévisualiser, auditer les volumes et obtenir l’accord de planification avant de confirmer.

## 6. Carte des sources exactes

| Domaine | Fichier du commit `70d08da` | Fonctions clés |
|---|---|---|
| Interface | `frontend/src/pages/getinjs/GenerationAnnuelle.jsx` | `lancerGeneration`, aperçu et confirmation |
| Campagnes | `backend/edts/moteur/campagnes.py` | `creer_campagne`, `executer_campagne`, `valider_campagne`, `publier_campagne` |
| Calendrier | `backend/edts/moteur/calendrier_previsionnel.py` | `proposer` |
| Orchestration annuelle | `backend/edts/moteur/annee.py` | `generer_annee`, `_generer_calendrier_provisoire` |
| Import inscrits | `backend/edts/moteur/import_inscrits.py` | `importer_inscrits` |
| Besoins | `backend/edts/moteur/besoins.py`, `besoins_maquette.py` | `calculate_teaching_needs`, `besoins_depuis_maquette` |
| Solveur et règles | `backend/edts/moteur/generation.py`, `contraintes.py`, `validation.py` | `generate_schedule`, `candidats`, `_backtrack`, `validate_schedule` |
| Écriture et API | `backend/edts/moteur/orchestration.py`, `publication.py`, `backend/edts/api_getinjs.py` | persistance, endpoints de campagne |

**Lecture :** ce document explique le logiciel ; le ZIP fournit les implémentations exactes du commit. Il ne contient ni données personnelles, ni dump de production, ni `.env`, ni secret.
