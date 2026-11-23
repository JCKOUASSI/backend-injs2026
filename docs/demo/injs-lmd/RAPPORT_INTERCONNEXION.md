# Rapport d’interconnexion

## Chaîne académique et EDT

`Référentiels INJS/LMD → Formation/Parcours/Niveau/Semestre → Maquette → UE → ECUE → Affectation pédagogique → Besoin horaire → AffectationCreneau → EmploiDuTemps`.

L’API de génération produit un plan contrôlé. Les placements manuels utilisent les mêmes contraintes de chevauchement, salle, enseignant, groupe et capacité. Le flux de publication est distinct de la génération.

## EDT vers application et présences

`EmploiDuTemps publié → AffectationCreneau actif → SeanceRegistre → Session QR temporaire → Pointage → audit / supervision / historique`.

Le registre de séances n’invente pas d’occurrence hors EDT. Les secrets QR ne sont pas enregistrés dans le journal d’audit et ne sont pas exportés dans le classeur.

## Autres chaînes présentes

- Admissions → inscriptions administratives → cohortes et groupes.
- Inscriptions → maquettes actives → demandes d’équivalence.
- Étudiants → conventions et évaluations de stage.
- Sessions d’évaluation → notes en brouillon.
- Finances → échéanciers et factures brouillon, paiements non confirmés.
- Personnel, administration, jurys et diplômation → jeux DEMO propres aux modules.

Les suites backend `edts.tests` et `presences` valident le raccordement EDT/Présences et les principales règles d’intégrité. Les pointages QR ne sont pas préremplis dans cette base.
