# Scénarios de démonstration INJS-LMD

Toutes les lignes générées par les commandes `seed_*_demo` sont classées DEMO. Les maquettes importées sont rattachées aux sources documentaires INJS; les éléments reconstitués sont signalés comme tels dans leurs commandes.

## 1. Référentiels → maquettes → affectations pédagogiques

Présenter les 16 formations, 40 maquettes actives de l’année 2026-2027, leurs UE/ECUE et les affectations pédagogiques. Le jeu contient 679 UE et 1 055 ECUE pour cette année; les totaux incluent des compléments provenant du référentiel LMD versionné. MS-S8 est marqué comme reconstitution à confirmer.

## 2. Cohorte → inscription → EDT

La cohorte de 5 000 étudiants DEMO est répartie à parité. Les affectations pédagogiques couvrent 1 055 ECUE. La commande GET INJS a créé 16 EDT publiés, 176 placements et 176 séances de registre utilisables par le module Présences. Une campagne est laissée à l’état **Prêt** afin de démontrer le lancement depuis l’écran des campagnes.

## 3. EDT → Présences QR

Ouvrir **Présences → Séances** ou **Badgeage** depuis le menu. Les routes principales sont `/presences/seances`, `/presences/poste` et `/presences/registre`. Les séances publiées sont raccordées au registre et les API de création/lecture du QR, scan, heartbeat, entrée/sortie, clôture et correction manuelle sont couvertes par les tests.

Aucun pointage QR fictif n’a été injecté dans la base. Le classeur agrégé affiche le nombre de pointages réel (zéro à la date du seeding) et n’exporte aucun secret de jeton.

## 4. Génération manuelle et automatique

- **Manuelle** : ouvrir `/edt`, créer/éditer un brouillon, placer ou déplacer des séances, consulter les conflits, puis soumettre et valider.
- **Automatique** : ouvrir `/edt/campagnes`, inspecter la campagne prête, lancer la génération, consulter l’audit, puis soumettre/valider/publier selon les habilitations.
- **Génération annuelle GET INJS** : `/edt/generation-annuelle`.

La publication reste une action explicite séparée de la génération. Les suites backend testent les deux types de placement et le workflow de validation/publication.

## 5. Autres modules renseignés

Admissions, équivalences, stages, administration, personnel, jurys, diplômation, évaluations et finances reçoivent des scénarios DEMO idempotents. Les paiements DEMO sont non confirmés et les notes restent en brouillon; aucun paiement réel ni résultat officiel n’est simulé.
