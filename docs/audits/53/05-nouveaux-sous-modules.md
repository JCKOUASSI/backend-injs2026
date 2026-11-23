# Livrable 5 — Nouveaux sous-modules

Chaque sous-module ci-dessous est justifié par un besoin métier identifié dans les documents source ; aucun n'est un habillage graphique.

| # | Sous-module | Modèle (table) | Justification métier | Source |
|---|---|---|---|---|
| 1 | **Écoles** | `referentiels.RefEcole` | Les deux écoles supérieures de l'INJS conditionnent les mentions, les filières et donc les cycles. Sans elles, aucune agrégation institutionnelle n'est possible | F1 §1 |
| 2 | **Mentions** | `referentiels.RefMention` | Rattachement disciplinaire STAPS / STASE exigé par les dossiers d'admission et les diplômes | F1 §2 |
| 3 | **Natures de cursus** | `referentiels.RefTypeCursus` | Sépare explicitement LMD / professionnel / continu / à la carte / concours — interdit mission de mélanger ces populations | F1 + cadrage §5.B |
| 4 | **Filières métier** | `referentiels.RefFiliere` | Les 8 filières F01–F08 sont la clé de rattachement de tous les cycles et modules. Le `code_dossier` rend le rapprochement déterministe | F1 §3 |
| 5 | **Modules officiels** | `referentiels.RefModuleOfficiel` | Nomenclature des 227 modules réellement enseignés : socle de la ventilation future en UE/ECUE et de la vérification des maquettes | F1 §5 |
| 6 | **Volumes horaires** | `referentiels.RefVolumeHoraireFormation` | Répartition CM/TD/TP/stage, explicitement « proposition » : sert au calcul de charge enseignante et à la génération d'emploi du temps, à condition de rester marquée `MODELISE` | F3 |
| 7 | **Types d'enseignement** | `referentiels.RefTypeEnseignement` | CM / TD / TP / Stage : nécessaire au calcul des heures complémentaires et à la lecture des volumes | F3 |
| 8 | **Statuts de vague** | `referentiels.RefStatutVague` | Cycle de vie d'une vague de recrutement (Prévisionnelle → Terminée), prérequis du module Admissions | F4 |
| 9 | **Tableau de bord Référentiels** | — (vue API `tableau-de-bord/`) | Sans vue d'ensemble, l'administrateur ne peut ni mesurer la complétude ni repérer les référentiels vides ou non sourcés | Cadrage §5 |
| 10 | **Écran générique de gestion** | — (React `ReferentielGenerique`) | Évite 14 écrans quasi identiques ; les sélecteurs dépendants (école → mention, école → filière) sont pilotés par le registre | Cadrage §6 |
| 11 | **Import documentaire idempotent** | — (commande `importer_referentiels_injs`) | Rend l'initialisation reproductible sur toute base neuve, avec provenance et sans doublon | Cadrage §7 |
| 12 | **Contrôle de cohérence** | — (commande `verifier_coherence_referentiels`) | Transforme les incohérences en constats numérotés au lieu de les masquer | Cadrage §7 |

## Détail des apports par rapport à l'existant

| Apport | Avant | Après |
|---|---|---|
| Provenance | Aucune colonne `source_document` sur les référentiels | Chaque entrée issue des documents porte sa source et sa fiabilité |
| Complétude | Inconnue | Compteurs `total`, `actifs`, `archives`, `a_renseigner`, `sans_source`, taux de traçabilité |
| Anti-doublon | Variable selon l'écran | Contrainte base + contrôle applicatif normalisé (casse/accents) sur tous les référentiels du registre |
| Historisation | Suppression possible sur certains écrans | Archivage réversible, journal `ReferentielJournal` (append-only) |
| Sélecteurs dépendants | Codés écran par écran | Déclarés dans le registre (`selecteurs` + `selecteurs_routes`) |

## Ce qui n'a **pas** été créé, volontairement

| Candidat | Raison du refus |
|---|---|
| Référentiel « crédits ECTS » | Aucun document ne fournit les crédits par module ; les créer serait une donnée fictive |
| Référentiel « décisions académiques V01–V14 » | Non confirmé par la source |
| Référentiel « règles de jury » | Interdit explicite de la mission |
| Référentiel « SYGEP » / « CPFAE » | Hors périmètre INJS (le corpus CPFAE a été explicitement exclu de l'import des volumes) |
| Doublon « Salles » vs « Types d'espace sportif » | Deux granularités différentes (espace physique vs typologie) : conservées séparément, la typologie restant `A_RENSEIGNER` |
