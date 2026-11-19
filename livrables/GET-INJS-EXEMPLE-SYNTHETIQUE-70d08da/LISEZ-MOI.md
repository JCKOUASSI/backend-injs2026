# GET INJS APP — exemple de jeu de données (SYNTHÉTIQUE)

**Version de code :** commit déployé `70d08dad1821caceb61b22fe22cf70e13155bf18`. **Nature :** démonstration inventée suivant les champs et les choix des modèles Django de cette version ; **aucune connexion à la base de production**, aucune extraction des inscriptions ou du planning réels. Les identifiants `900001`–`901101`, noms `DEMO`/`FICTIF` et intitulés sont inventés. Le code de filière `F01` illustre seulement le format attendu et ne signifie pas que cette formation fictive est reconnue par l’INJS. Les dates de l’année `2026-2027` suivent les **bornes provisoires** retenues pour l’exploitation (`01/10/2026`–`30/09/2027`), non un calendrier institutionnel définitif. L’horodatage des lignes est fictif.

**Ne pas importer ces fichiers.** Ils servent à lire la structure et à tester des traitements sur des copies isolées après adaptation et validation, non à alimenter la production. Il n’y a ni étudiants réels, ni compte utilisateur utilisable, ni enseignant, ni salle, ni mot de passe, ni séances publiées.

## Contenu

- `GET-INJS-EXEMPLE-SYNTHETIQUE-70d08da.json` : 28 tables du périmètre GET INJS avec les colonnes du code déployé ; **13 lignes fictives** réparties sur **12 tables**, les 16 autres volontairement vides.
- `*.csv` : un fichier par table, avec en-tête **exactement conforme aux colonnes du modèle**. Encodage UTF-8 avec BOM, séparateur `;`, JSON dans les cellules des colonnes JSON. Les fichiers sans lignes ne représentent **pas** le nombre de lignes réel en production.
- `MANIFESTE-SHA256.txt` : empreinte des fichiers du jeu de données inclus.

## Lecture du scénario fictif

```text
Année 2026-2027 (id 900001 ; bornes provisoires)
  └─ formation fictive DEMO-F01 (id 900101)
      ├─ parcours DEMO-P1 (900301) ; niveau DEMO-L1 (900201)
      ├─ groupe DEMO-G1 (900501), semestre 1 (900401)
      │   └─ inscriptions importées FICTIF/Exemple Un et Deux (901001/901002)
      └─ maquette BROUILLON (900601)
          └─ UE BROUILLON (900701) → ECUE BROUILLON (900801)
Créneau-type du lundi (900901) : référentiel isolé, sans affectation.
Campagne BROUILLON (901101) : simple intention, jamais exécutée.
```

Le code déployé conserve CM/TD/TP dans `scolarite_ecue`. Ici, les trois champs valent `0.00` **uniquement parce que la démonstration n’a aucun volume confirmé**. Ils **ne signifient PAS** que CM, TD ou TP sont officiellement inapplicables, et **ne doivent pas être utilisés pour calculer ou publier un EDT**. Il n’existe dans cet exemple aucune `ExecutionCampagne`, aucun `EmploiDuTemps`, aucune `AffectationCreneau` ou `SeanceRegistre`. Ceci évite de présenter une génération fictive comme réalisée. La campagne reste au statut `BROUILLON` ; la maquette/UE/ECUE aussi.

## Aperçu de colonnes

| Table | ID fictif | Éléments illustrés |
|---|---:|---|
| `scolarite_anneeacademique` | 900001 | `libelle`, `date_debut`, `date_fin`, `fiabilite=A_RENSEIGNER` |
| `formations_refformation` | 900101 | `perimetre=INJS`, `filiere_code=F01` (code de démonstration) |
| `scolarite_groupe` | 900501 | FK vers année, formation, parcours et niveau |
| `scolarite_maquette` | 900601 | FK vers année, formation, parcours et niveau ; `statut=BROUILLON` |
| `scolarite_ue` / `scolarite_ecue` | 900701 / 900801 | FK pédagogiques ; volumes **inconnus**, non validés |
| `edts_inscriptionimportee` | 901001, 901002 | matricules `DEMO-ETU-*`, groupe et cohorte fictifs |
| `edts_campagnegeneration` | 901101 | une semaine illustrative, groupe fictif, `statut=BROUILLON` |

## Limites

Ce n’est **ni une sauvegarde ni un échantillon anonymisé** de la base actuelle. Les chiffres opérationnels, les identités, les volumes officiels, la répartition horaire et l’état réel des campagnes **ne peuvent pas être déduits** de cet exemple. Pour le schéma documentaire intégral des 357 colonnes et 83 relations, consulter le livrable `GET-INJS-SCHEMA-70d08da.zip`. Une extraction réelle demanderait un accès administrateur à la production, un périmètre explicite et des mesures de confidentialité ; aucune n’a été effectuée ici.
