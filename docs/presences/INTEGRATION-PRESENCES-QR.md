# Intégration — Présences QR + géolocalisation (chaîne LMD)

*État : finalisation du module existant (audit + compléments), aucun second
système. Ce document décrit le comportement RÉEL du code, pas un cahier des
charges.*

## 1. Chaîne métier réelle

```
Groupe → EmploiDuTemps (PUBLIE) → AffectationCreneau (séance)
      → QRToken(seance_edt) → Badgeage → Pointage → Présence (consultation)
```

Une seule séance fait foi : `edts.AffectationCreneau`. Une seule présence :
`presences.Pointage` (FK `seance_edt`). Un seul jeton QR : `formations.QRToken`
(colonne `seance_edt`). Un seul mécanisme de heartbeat : les endpoints
`/api/scan/secure/*` (le serveur route selon le jeton : `seance_edt` → canal
LMD, `session` → canal legacy). Une seule autorité géofence :
`presences/geofence.py`. Un seul journal : `presences.AuditLog`.

## 2. Endpoints (canal LMD)

| Endpoint | Rôle | RBAC |
|---|---|---|
| `GET /api/presences/seances-edt/du-jour/` | séances du jour de l'appelant | authentifié + visibilité |
| `GET/POST /api/presences/seances-edt/{id}/qr/` | consultation / ouverture-régénération du QR | `peut_gerer_seance` |
| `POST /api/presences/seances-edt/scan/` | badgeage navigateur/enseignant | authentifié + `autorisation_badgeage` |
| `GET /api/presences/seances-edt/{id}/presences/` | liste + synthèse (attendus/présents/retards/absents/manuelles/anomalies) | `peut_gerer_seance` |
| `POST /api/presences/seances-edt/{id}/emargement/` | émargement de masse à motif (sémantique historique conservée) | `ExigePermission(presences.emargement.saisir)` + `peut_gerer_seance` |
| `POST /api/presences/seances-edt/{id}/emargement/unitaire/` | **badgeage manuel unitaire** (catalogue de motifs) | idem |
| `POST /api/presences/seances-edt/{id}/autoclore/` | clôture automatique de séance | `ExigePermission(...cloturer)` + `peut_gerer_seance` |
| `POST /api/scan/secure/` | scan mobile (entrée puis sortie, toggle) | authentifié, identité = compte |
| `POST /api/scan/secure/heartbeat/` | heartbeat géolocalisé unique | authentifié |
| `POST /api/scan/secure/exit/` | **sortie volontaire** (canaux LMD et legacy) | authentifié |
| `GET /api/scan/secure/check-status/` | état du prochain badgeage | authentifié |
| `GET /api/me/historique/` | historique personnel (badgeages, dont canal `EDT_LMD`) | authentifié |

L'identité n'est JAMAIS lue dans le corps de la requête : elle est déduite du
compte authentifié (`_resolve_authenticated_personne`). Les champs client
(`inside_geofence`, `role`, `participant_id`…) ne sont pas lus. Latitude,
longitude et précision ne figurent dans aucune réponse publique (elles ne
vivent que dans `Pointage.last_*`, le journal d'audit et les vues réservées
aux rôles habilités).

## 3. Badgeage QR (automatique)

- Fenêtre : paramètres projet existants (ouverture anticipée 10 min,
  tolérance retard 10 min, clôture = fin + tolérance paramétrée).
- Entrée : géofence vérifiée CÔTÉ SERVEUR (`geofence.verifier_position`,
  rayon = `RefSite.geofence_rayon_m` — salle → `RefSalle.site`, repli site
  actif unique — précision max `MOBILE_GEOFENCE_MAX_ACCURACY_M`=80 m).
  Refus : `OUT_OF_GEOFENCE`, `LOCATION_INACCURATE`, `LOCATION_REQUIRED` ;
  aucune ligne créée sur refus.
- Deuxième scan = sortie (toggle) ; troisième scan = `ALREADY_SCANNED`
  (normalisé `DOUBLE_ENTREE`). Séance annulée → le jeton devient invalide
  (`QRToken.is_valid`) → refus `QR_EXPIRE`. QR régénéré : l'ancien jeton
  suit son remplaçant actif (`resoudre_jeton_lmd`), sinon `QR_EXPIRE`.
- Anti-rejeu : le QR est un jeton PARTAGÉ de séance — l'unicité par personne
  est portée par `Pointage` (une entrée, une sortie), la fenêtre et la
  désactivation des jetons à la clôture. Aucun nonce par étudiant n'existe
  ni n'est requis : le QR ne porte aucune identité, l'identité est le compte.

## 4. Mode, motif, nature de sortie (migration additive `presences.0030`)

Champs ajoutés à `Pointage` (aucun backfill : l'historique reste `NULL` =
« non renseigné », lisible via `device_id` pour les lignes anciennes) :

- `mode` : `QR_AUTOMATIQUE` (scan/sortie) ou `MANUEL` (émargement de masse,
  badgeage unitaire, correction). Les lignes système de la clôture
  (absents non badgés) restent `NULL` : ce ne sont pas des badgeages.
- `motif_manuel`, `commentaire_manuel` : posés par les gestes manuels.
- `type_sortie` : `SORTIE_QR` (sortie volontaire : second scan ou endpoint
  de sortie) ou `SORTIE_AUTOMATIQUE_FIN_SEANCE` (autoclôture, sortie auto
  heartbeat, commande d'auto-clôture). Le journal d'audit relaie la même
  valeur dans `extra.type_sortie`.

Par événement, le journal consigne `source_position` : `BADGE_ENTREE`,
`BADGE_SORTIE`, `HEARTBEAT` (avec `evaluation`), et pour les gestes manuels
le motif + `avant`/`après` en cas de correction.

## 5. Badgeage manuel (exception tracée, jamais un défaut)

Catalogue (`seances_edt_services.MOTIFS_EMARGEMENT_MANUEL`) :
`QR_NON_LISIBLE`, `GPS_INDISPONIBLE`, `PANNE_RESEAU`, `PROBLEME_TECHNIQUE`,
`PARTICIPANT_PRESENT_SANS_BADGE`, `AUTRE` (commentaire obligatoire).

- Unitaire : `POST …/emargement/unitaire/` `{participant, statut?, motif,
  commentaire?}` → `201 {mode: MANUEL, …}`. Erreurs : `MOTIF_MANUEL_REQUIS`
  (400), `MOTIF_MANUEL_INCONNU` (400), `COMMENTAIRE_MANUEL_REQUIS` (400),
  `NOT_IN_GROUP` (403), 403 sans la permission CURP/garde de gestion.
- Masse (historique) : sémantique inchangée (motif libre, obligatoire
  seulement pour corriger une ligne existante) ; pose désormais aussi
  `mode=MANUEL` pour que la synthèse compte les présences manuelles sans
  déduction fragile.

## 6. Heartbeat et géolocalisation

Même endpoint pour les deux canaux. Côté LMD, chaque réponse porte
désormais `evaluation` : `DANS_PERIMETRE`, `HORS_PERIMETRE`,
`POSITION_IMPRECISE` (précision > seuil projet), `POSITION_ABSENTE`
(aucune coordonnée alors que le site est géolocalisé). Règles métier
existantes inchangées : hors périmètre → présence conservée, statut
`HORS_LIGNE_SUSPECT` ; après `MOBILE_GEOFENCE_OUTSIDE_CONFIRMATIONS`
confirmations (défaut 2) → `SORTIE_AUTO` (+ `type_sortie` automatique).
Aucun tracking permanent nouveau : le heartbeat ne vit que pendant la
séance ouverte, déclenché par l'application cliente.

## 7. Sortie volontaire

`POST /api/scan/secure/exit/` `{token_qr, device_id, latitude?, longitude?,
accuracy_m?}` : ferme le pointage OUVERT de l'appelant sur la séance du
jeton. Sans entrée ouverte → `400 SORTIE_SANS_ENTREE` (code legacy
`NO_OPEN_SESSION`), aucune ligne créée. La sortie n'est jamais refusée
pour un motif de géofence ; une position transmise est consignée dans
l'audit (`via: ENDPOINT_SORTIE`). Le client Flutter dispose de
`ScanService.secureExit` + `SessionProvider.requestSecureExit` ; le scan
toggle reste fonctionnel pour les écrans existants.

## 8. Codes d'erreur

Le code legacy (`code`) et `detail` sont INCHANGÉS (compatibilité Flutter
et web). Les réponses du canal LMD ajoutent, sans substitution :
`code_normalise`, `message`, `action_recommandee`
(`seances_edt_services.normaliser_erreur`) :

| Legacy | Normalisé |
|---|---|
| `INVALID_TOKEN` | `QR_INVALIDE` |
| `TOKEN_EXPIRED` | `QR_EXPIRE` |
| `ALREADY_SCANNED` | `DOUBLE_ENTREE` |
| `NOT_IN_LIST` / `NOT_IN_GROUP` | `ETUDIANT_HORS_GROUPE` |
| `UTILISATEUR_NON_AUTORISE` (formateur) | `ENSEIGNANT_NON_AFFECTE` |
| `UTILISATEUR_NON_AUTORISE` (encadrant) | `ACTIVITE_NON_AUTORISEE` |
| `HORS_SEANCE` / `TROP_TOT` | `SEANCE_INACTIVE` |
| `HORS_FENETRE` | `SEANCE_TERMINEE` |
| `OUT_OF_GEOFENCE` | `HORS_GEOFENCE` |
| `LOCATION_REQUIRED` | `GPS_INDISPONIBLE` |
| `LOCATION_INACCURATE` | `PRECISION_GPS_INSUFFISANTE` |
| `NO_OPEN_SESSION` | `SORTIE_SANS_ENTREE` |

`QR_REUTILISE` n'est pas émis : la détection est par personne sur
`Pointage` (`DOUBLE_ENTREE`), pas par jeton. Les statuts HTTP sont
conservés (400 métier, 403 autorisation/RBAC).

## 9. Encadrants (habilitation explicite)

Un encadrant badgé sur une séance LMD n'est ni un enseignant ni un
étudiant : son habilitation est la liaison `presences.EncadrantSeance`
(encadrant ↔ `AffectationCreneau`, `actif`, `cree_par` ; unicité par
couple ; `on_delete=PROTECT`), gérée dans l'admin Django.
`autorisation_badgeage` : intervenant désigné OU encadrant habilité ;
sinon 403 `ACTIVITE_NON_AUTORISEE`. `peut_gerer_seance` ouvre aussi la
gestion (émargement) à l'encadrant habilité. Le canal legacy module garde
son rattachement par module (superviseur), inchangé.

## 10. Suppression d'une séance

`Pointage.seance_edt` est en CASCADE (historique) : la protection métier
reste celle de la chaîne EDT (interopérabilité `edts.moteur.interop_presences`,
identité stable des séances publiées) et des `PROTECT` posés sur les
liaisons d'habilitation. Aucun comportement de suppression n'a été modifié.

## 11. Limites connues (assumées, documentées)

- L'historique antérieur à la migration 0030 n'a ni `mode` ni `type_sortie`
  (aucune requalification inventée).
- Le web n'a pas de scanner temps réel : le badgeage navigateur passe par
  l'écran enseignant (QR affiché + scan étudiant mobile).
- Le bouton Flutter de sortie dédiée repose sur `requestSecureExit`
  (fourni) ; les écrans actuels utilisent le scan toggle. `flutter analyze`
  et `flutter test` ne sont pas exécutables dans l'environnement de
  livraison (SDK absent) : le code Dart ajouté suit strictement les patrons
  existants (`secureScan`/`heartbeat`).

## 12. Contrat d'API figé

Le snapshot `docs/api/contract.snapshot.json` n'a PAS été régénéré : la
base figée du dépôt est antérieure à plusieurs lots déjà livrés (la
régénération absorberait ~745 routes sans rapport avec cette mission).
Le test de contrat (`config.tests.test_api_contract`) tolère les ajouts
et passe inchangé : les deux routes nouvelles sont des extensions
strictement additives. La régénération du snapshot reste une action de
gouvernance du dépôt, à mener avec `update_api_contract` et sa
justification.

## 13. Commandes de vérification

```bash
cd backend
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test presences formations
python manage.py test            # suite complète
# Ne PAS migrer la base de développement sans plan explicite :
# python manage.py migrate presences   # ajoute 0030 (additif, sans perte)
```

```bash
cd frontend && npm test && npm run build
```

## Hub web « Présences QR » (refonte complète)

Écran Présences de séance : design « Nuit INJS Premium Dynamique »
(validé sur maquette `designs/presences-seance-premium.html`) — bandeau
nuit avec pastille EN DIRECT, panneau QR réel (jeton serveur, jamais un
faux QR), synthèse à anneau de taux, avatars étudiants, filtres
segmentés + recherche instantanée, état vide premium avec navigation
par jour. Design du tableau de bord : « Nuit INJS Premium » (validé sur maquette
`designs/tableau-de-bord-presences-premium.html`) — bandeau nuit
académique à chiffres héros, plaquettes verre dépoli, accent doré,
anneau de retard moyen ; données strictement serveur.

Le module est exposé comme un **hub autonome** dans la barre latérale
(section « Présences QR », immédiatement après « GET INJS APP »), aligné
sur les modules de l'application de référence « GET INJS Présences QR ·
Géolocalisation ». Chaque écran est adossé aux endpoints Django
existants — aucune architecture parallèle :

| Écran | Route | Source(s) serveur |
|---|---|---|
| Tableau de bord | `/presences` | supervision enrichie (séances, volume horaire, étudiants/enseignants présents-attendus, en salle/espace maintenant, retard moyen, sessions QR, émargements manuels, répartition par population) + audit (heartbeat, derniers pointages). Plaquettes alignées INJS : Étudiants, Enseignants, « En Salle/Espace maintenant » ; bloc Services académiques limité aux formations du jour (masqué sinon) |
| Présences de séance | `/edt/presences` | QR, émargement, clôture (enseignant de la séance) |
| Séances (registre refondu) | `/presences/seances` | `GET /api/presences/seances-edt/supervision/?date=&statut=` (filtres serveur, identifiant permanent `INJS-S-######`, ECUE → UE, encadrants habilités, attendus/présents/manuels/anomalies) ; mode **chargement explicite** `&limite=200&horizon=120` : 200 séances les plus proches de la date repère (jours candidats par proximité, bloc `periode`, résumé recalculé sur la sélection) |
| Poste de badgeage | `/presences/poste` | QR + `POST /presences/seances-edt/scan/`, heartbeat `/scan/secure/heartbeat/`, sortie `/scan/secure/exit/` |
| Présences (registre historique refondu) | `/presences/registre` | `GET /api/presences/seances-edt/historique/` (registre transversal) + `GET /presences/seances-edt/du-jour/` et `GET /presences/seances-edt/{id}/presences/` (exceptions du jour) |
| Journal d'audit (traçabilité non destructive) | `/presences/audit` | `GET /api/audit-logs/` (lecture seule) : articles horodatage/auteur/entité, puce d'action (alerte = intervention humaine), motif, ancienne/nouvelle valeurs (`extra.avant`/`apres`) côte à côte ; chargement explicite des **200 événements les plus récents** (`?limite=200`, paramètre additif plafonné à 500, défaut historique inchangé), affichés en **liste compacte déployable** (une ligne par événement, détail au clic) **paginée par 12** |
| Configuration géofence | `/presences/configuration` | `GET|POST|PUT /api/formations/ref/sites/` (DFRC) |
| Contrat API | `/presences/contrat` | documentation intégrée des contrats réels |

Écrans complémentaires (hors menu du module, atteignables depuis le
tableau de bord et les contrôles d'anomalies) : registre nominatif
détaillé `/presences/registre` (`GET /api/presences/seances-edt/{id}/presences/`)
et rattrapages inter-cohorte `/rattrapages`.

### Registre historique « Présences » (refondu)

L'entrée **Présences** du menu du module pointe désormais sur
`/presences/registre` : un **registre historique transversal** inspiré
de l'application de référence, adossé à un endpoint additif :

`GET /api/presences/seances-edt/historique/?date_debut=&date_fin=&type=&mode=&nom=&groupe=&seance_id=`
→ `{date_debut, date_fin, total, resultats[]}`

- **Périmètre** : uniquement les séances EDT `VALIDE`/`PUBLIE` — le
  rôle privilégié voit tout, l'enseignant/encadrant ne voit que ses
  séances (affectation de créneau, inscription de groupe ou
  `EncadrantSeance`). Aucun pointage hors de ce périmètre n'est exposé.
- **Chaque ligne** : participant + type **réel** (ÉTUDIANT / ENSEIGNANT /
  ENCADRANT déduit de la FK du pointage, jamais du nom), séance + groupe,
  entrée, sortie, **nombre de heartbeats** comptés dans l'audit
  (`SCAN_HEARTBEAT`), durée (`duree_presence_minutes`, jamais inventée),
  mode QR/manuel avec **motif et auteur manuel** (dernier
  `AuditLog FORCE_ENTREE` — le `Pointage` ne porte pas d'auteur), verdict
  de périmètre **déduit** (`MANUEL` → aucun ; sorties hors périmètre /
  signal perdu via compteurs et `statut`), précision `± m` arrondie,
  assiduité, anomalies (hors périmètre, signal perdu, position imprécise,
  entrée forcée, hors ligne suspecte, sortie automatique tracée).
  **Aucune coordonnée GPS n'est renvoyée** ; extraction bornée (slice 500).
- **Côté web** : filtres serveur (période, nom, groupe, type, mode,
  séance) synchronisés avec l'URL — l'arrivée tableau de bord
  `?seance=&date=` reste compatible — compteurs du hero relus de la
  réponse serveur (pointages présentés, badgeages manuels), légende
  « verdict GPS calculé au moment du pointage — coordonnées brutes
  jamais affichées ».
- **Section « Émargement manuel et corrections »** : sélecteur de séance
  du jour, lignes participants et réutilisation de la modale
  `ModalBadgeageManuel` (badgeage manuel unitaire à motif obligatoire —
  l'acteur est le compte connecté, tracé côté serveur, **aucun sélecteur
  d'acteur libre**) ; lien vers l'émargement complet `/edt/presences`.
  RBAC · motif · audit, conformément à la mission.

Règles respectées dans tous les écrans : le serveur reste l'autorité
(aucun verdict recalculé côté navigateur — la « simulation » de la page
géofence est explicitement non opposable), canal QR/manuel toujours
identifiable (`mode`, `motif_manuel`, `type_sortie`), erreurs affichées
sous forme normalisée (`code_normalise`, `message`, `action_recommandee`),
aucune coordonnée GPS dans les réponses publiques.
