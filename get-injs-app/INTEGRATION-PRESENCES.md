# Intégration du futur module Présences avec GET INJS APP

Guide contractuel pour le développeur du module de gestion des présences
(QR Code, pointage manuel, géolocalisation). **Rien dans ce document n'est
à reconstruire côté GET** : les fondations ci-dessous sont implémentées,
migrées et testées (14 tests dans `backend/edts/tests/test_interop_presences.py`).

Principe directeur : **une séance pédagogique officiellement publiée dans
GET est la référence métier de tout pointage.** GET ne produit ni pointage,
ni QR Code, ni statistique de présence.

---

## 1. Schéma des entités (tables `gi_*`, app Django `edts`)

```
EmploiDuTemps (existant) 1───* AffectationCreneau (séance hebdomadaire, existant)
                                   │ 1
                                   │ (OneToOne, SET_NULL)
                                   ▼ 0..1
                            SeanceRegistre  (gi_seance_registre)
                              uuid (unique, permanent) · cle_metier (unique, SHA-256)
                              statut · version · publie_le/par · motif_annulation
                              cree_par · modifie_par
                                   │ seance_origine (FK self, annulation→reprogrammation)
                                   ├──* SeanceHistorique (gi_seance_historique)
                                   ├──* SeanceEvenement (gi_seance_evenement)
                                   └──* SeanceInstantaneAttendus (gi_seance_instantane)

formations.RefSalle (existant) 1───0..1 SalleGeolocalisation (gi_salle_geolocalisation)
presences.Pointage.seance_edt ───► AffectationCreneau (lien existant, protégé)
```

Le contexte académique (année, formation, parcours, niveau, semestre, UE,
ECUE, maquette via `scolarite.AffectationPedagogique`, groupe, enseignant,
salle) est **toujours retrouvé par relations** — aucune redondance stockée.

## 2. Cycle de vie d'une séance

```
BROUILLON ──► SIMULATION ──► BROUILLON            (simulation ≠ officiel)
   │              │
   ├──► EN_ATTENTE_VALIDATION ──► VALIDEE ──► PUBLIEE ──► MODIFIEE ──► PUBLIEE
   │                                   │          │           │
   └──────────────► ANNULEE ◄──────────┴──────────┴───────────┘
PUBLIEE / MODIFIEE ──► TERMINEE (clôturée, historique préservé)
```

Règles : identité (UUID) conservée lors de toute modification ordinaire ;
modification après publication ⇒ statut `MODIFIEE`, version incrémentée,
historique + événement ; annulation motivée et terminale ; reprogrammation
= nouvelle séance reliée par `seance_origine` ; suppression physique
interdite si un pointage référence la séance (`ProtectedError`).

**Ouverture de session de présence** : autorisée si et seulement si le
statut est `PUBLIEE` ou `MODIFIEE` (`peut_ouvrir_session_presence`).

## 3. Contrat API (préfixe `/api/edts/interop/`, alias `/api/timetable/interop/`)

| Méthode | Route | Rôle minimum | Réponse |
|---|---|---|---|
| GET | `seances-publiees/?annee&formation&groupe&page&page_size` | authentifié | `{count, page, page_size, results: [contexte…]}` |
| GET | `seances/<uuid>/` | authentifié | contexte complet + 10 dernières traces |
| GET | `seances/<uuid>/etudiants-attendus/?date=` | authentifié | `{base, groupe_id, effectif, etudiants[]}` |
| POST | `seances/<uuid>/instantane/` | planification | instantané figé (201) |
| POST | `seances/<uuid>/transition/` `{statut, motif}` | planification ; `VALIDEE/PUBLIEE/TERMINEE` ⇒ DIRECTION/ADMIN | contexte à jour |
| POST | `emplois/<id>/reconcilier/` | planification | `{crees, rattaches, existants, publiees}` |
| GET | `salles-geolocalisation/` | authentifié | salles + configuration géo |
| GET | `evenements/?apres=<id>&non_consommes=1` | authentifié | file d'événements (max 200) |

### Contexte d'une séance (extrait)

```json
{
  "seance_uuid": "d2d9dd0e-…",
  "statut": "PUBLIEE",
  "version": 1,
  "publie_le": "2026-11-04T…",
  "peut_ouvrir_session_presence": true,
  "seance_origine_uuid": null,
  "placement": {
    "annee_academique": "2026-2027",
    "formation": "ÉDUCATION ET MOTRICITÉ — LICENCE",
    "niveau": "L1", "semestre": "S1",
    "ue": "EM-S1-UE03", "ecue": "EM-S1-UE03-EC01",
    "groupe_id": 12,
    "jour": "LUNDI", "heure_debut": "08:00", "heure_fin": "10:00",
    "duree_prevue_minutes": 120, "fuseau_horaire": "Africa/Abidjan",
    "type_seance": "COURS",
    "enseignant": "…",
    "salle": {"id": 3, "nom": "Amphithéâtre A", "capacite": 200,
      "geolocalisation": {"latitude": "5.2959000", "longitude": "-3.9861000",
        "rayon_tolerance_m": 120, "type_espace": "AMPHITHEATRE",
        "statut_configuration": "CONFIGUREE", "coordonnees_disponibles": true}}
  }
}
```

### Événements (à consommer par curseur croissant)

`SEANCE_PUBLIEE`, `SEANCE_MODIFIEE`, `SEANCE_ANNULEE`,
`SEANCE_REPROGRAMMEE` (la charge utile relie `seance_annulee_uuid`),
`SEANCE_CLOTUREE`. Charge utile : uuid, statut, version, jour, horaires,
salle, groupe, formateur. Le futur module marque `consomme` côté GET via
son propre suivi d'id — la file GET reste append-only.

## 4. Dictionnaire des données utiles au pointage

| Donnée | Source contractuelle | Remarque |
|---|---|---|
| Identité séance | `SeanceRegistre.uuid` | permanent, indépendant date/salle/enseignant |
| Statut officiel | `SeanceRegistre.statut` | `PUBLIEE`/`MODIFIEE` seuls exploitables |
| Date d'occurrence | à calculer : `rentree` de l'EDT + semaine + jour du créneau | le placement est hebdomadaire récurrent |
| Horaires | `CreneauTemplate.heure_debut/fin`, fuseau `Africa/Abidjan` | durée prévue incluse |
| Étudiants attendus | endpoint dédié / instantané | voir §5 |
| Enseignant responsable | contexte `placement.enseignant` (affectation pédagogique) | associés via affectations du même ECUE |
| Lieu + géo | contexte `placement.salle.geolocalisation` | voir §6 |
| Historique | `SeanceHistorique` via le détail de séance | acteur, motif, avant/après |

## 5. Rattachement des étudiants aux séances

- Calcul vivant : membres **actifs** du groupe (`AffectationGroupe.active`)
  rattachés à un dossier étudiant ayant un participant — même périmètre
  que `presences.seances_supervision`. La réponse distingue l'inscription
  administrative source ; elle ne présume jamais l'inscription pédagogique.
- Instantané : `POST …/instantane/` fige `{participant_id, matricule, nom,
  prenom}` + effectif + règle de calcul. À constituer à l'ouverture d'une
  session de présence pour garantir la cohérence historique.
- Changement de groupe : les `AffectationGroupe` portent l'appartenance
  courante ; l'instantané préserve l'état à la date d'ouverture.

## 6. Configuration géographique des salles

Une ligne par salle (`SalleGeolocalisation`, OneToOne vers
`formations.RefSalle`) : latitude, longitude, rayon de tolérance (m),
zone, type d'espace, statut de configuration. La géolocalisation **n'est
pas une preuve de présence à elle seule** : le futur contrôle combinera
QR dynamique signé côté serveur, position déclarée + précision GPS,
horaire de séance et validation humaine. Aucune coordonnée GPS
d'étudiant n'a vocation à devenir une donnée académique permanente.

## 7. Matrice des permissions

| Action | Rôles |
|---|---|
| Consulter séances publiées, attendus, salles, événements | tout compte authentifié |
| Créer instantané, réconcilier un EDT, transitions ordinaires | planification EDT (ADMIN, CHEF_INJS_ADMIN, INJS_ADMIN, SECRETARIAT, CHEF_SECRETARIAT, DIRECTION, ENCADRANT) |
| Valider, publier, clôturer une séance | DIRECTION, ADMIN |
| Pointer / corriger une présence (futur) | **permissions propres au module Présences** — jamais héritées de la planification |

## 8. Ce qui reste à développer (module Présences, hors périmètre actuel)

Sessions de présence et jetons QR temporaires signés, moteur de pointage
(QR + manuel tracé : intervenant, horodatage, ancienne/nouvelle valeur,
motif, validateur), contrôles géographiques effectifs, statistiques de
présence et d'assiduité. Aucune de ces briques n'exige de refonte de GET :
le contrat ci-dessus suffit à les brancher.
