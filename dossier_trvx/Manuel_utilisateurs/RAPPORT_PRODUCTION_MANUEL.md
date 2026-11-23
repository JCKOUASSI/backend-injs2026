# Rapport de production — Manuel Utilisateur INJS LMD 2026

**Date :** 15 novembre 2026 · **Édition :** 2.0 avec réserves · **Branche de travail :** `arena/a8060ecf-backend-injs2026` (branche imposée par la session Arena ; **pas `main`**).

## 1. Audit et sources

- Source primaire examinée : applications/modèles Django, vues et routes API pertinentes, `frontend/src/App.jsx`, `frontend/src/menu/arborescence.js`, `authentication/models.py` et `role_groups.py`, catalogues `habilitations/referentiel/catalogue_matrice.py` et `catalogue_modules.py`, tests de menu/API et documentation existante.
- Corpus antérieur réutilisé avec **avertissement par chapitre** : édition du 9 novembre 2026 dans `arena/documentation/manuel_utilisateur/sources/` ; 12 parties et **44 chapitres**. Il ne suffit pas à prouver l'état des interfaces actuelles.
- **20 domaines** du catalogue d'habilitations ; **125 chemins** de menu statiques relevés dans l'arborescence courante (des écrans supplémentaires peuvent dépendre de routes génériques). **12 rôles applicatifs** de `User.Role`, distincts des **81 rôles catalogue** extraits pour la documentation antérieure. Deux codes (`FORMATEUR`, `AUDITEUR`) sont mobiles uniquement selon `role_groups.py` ; le reste exige une vérification de portée et de permissions effectives.
- **34 cas pratiques** C01–C34, dont les routes figurent dans le menu courant (sauf `/import`, interface legacy explicitement signalée dans le tableau d'import). **10 étapes** de configuration, **12 étapes** de parcours fictif, **16 problèmes** de dépannage et **11 limites** L01–L11. Matrice indicative : **240 lignes** profil × module avec preuve de catalogue, mais **pas** une recette des permissions API par ressource.
- Les captures intégrées (5 occurrences provenant des archives du dépôt, plus le logo institutionnel existant) sont des **captures existantes** ; aucune capture fabriquée n'est présentée comme réelle. Elles peuvent représenter une version d'interface antérieure.

## 2. Fichiers produits et contrôles

| Format | Contrôle réel | Résultat / réserve |
| --- | --- | --- |
| DOCX | Ouvert avec `python-docx` ; 717 paragraphes, 41 tableaux, 6 images ; champs TOC et PAGE détectés dans les parties XML. | Éditable ; sommaire Word à actualiser dans Word. Conversion visuelle par Microsoft Word non vérifiée ici. |
| PDF | Ouvert avec `pypdf` et rendu avec PyMuPDF ; **61 pages**, toutes non vides, pages 1/3/15 inspectées ; liens de sommaire internes valides (80 testés sur pages 2–3). | A4 lisible ; PDF produit depuis la même structure documentaire, pas converti du DOCX par LibreOffice (absent). Mise en page différente, contenu aligné ; absence de signets latéraux. |
| XLSX | Ouvert avec `openpyxl` ; **15 feuilles**, 15 filtres, 15 volets figés, 14 liens internes de sommaire, validation de données et mise en forme conditionnelle sur la matrice. | Outil complémentaire ; les états « Conditionnel » ne sont pas des droits garantis. |
| HTML | Analysé avec `lxml` ; 182 identifiants uniques, **105 liens internes**, 0 cible manquante, 6 images (logo compris), CSS et JS intégrés. | Autonome hors ligne ; recherche textuelle par bloc, sommaire et impression. Recette manuelle sur navigateurs mobiles non effectuée. |

Les identifiants C01 et C34, l'étudiant **fictif** KOUASSI Jean-Baptiste, les limites et la matrice figurent dans les sorties de référence. Les informations du XLSX sont structurées par ligne plutôt que copiées textuellement du manuel. Vérification de sécurité automatisée de chaînes d'identifiants connues : aucune chaîne détectée ; relecture institutionnelle toujours nécessaire.

## 3. Précautions et limites

1. **Aucune authentification de production ni opération de production** : pas de recette de chaque écran, drapeau ou statut sur le site public ; les cas se jouent en recette avec un compte autorisé.
2. Les profils métiers proposés par le catalogue ne doivent pas être confondus avec les 12 codes de rôle applicatif. La matrice N0–N4 renseigne des capacités **conditionnelles** et ne remplace pas les `permission_classes`, les droits effectifs et les restrictions d'objet.
3. Les 44 chapitres du manuel antérieur sont clairement marqués **non validés pour chaque compte dans la version courante** : ne pas réutiliser une ancienne étiquette de bouton sans vérifier l'écran.
4. Certaines fonctions (génération annuelle sans calendrier S1/S2, console CURP sans drapeau, badgeage web selon configuration) ne sont pas automatiquement ouvertes. Finances étudiantes ≠ comptabilité générale.
5. Le HTTP 500 de `/api/dashboard/overview/` constaté sur l'environnement de l'utilisateur n'est pas diagnostiqué sans exception serveur ; la réponse 200 de l'aperçu local ne prouve pas la résolution publique.
6. Aucun logiciel Word/LibreOffice disponible pour vérifier la fidélité de la conversion DOCX→PDF ; un rendu PDF cohérent est généré séparément depuis la même source. Ce point reste à valider avant publication institutionnelle.
7. Les imports/exports sont documentés **par écran**, sans extrapoler un format à tous les modules. Les fichiers d'exemple dans le manuel sont illustratifs, pas des modèles d'import garantis.

## 4. Git et verdict

Seuls `dossier_trvx/Manuel_utilisateurs/` et `scripts/produire_manuel_injs_2026.py` sont concernés par cette livraison documentaire. Aucun déploiement, accès VPS ou changement de base n'a été réalisé pour cette mission. La demande de push direct sur `main` est incompatible avec la branche fixe de cette session ; le commit et le push se font sur `arena/a8060ecf-backend-injs2026` uniquement. Le hash et le résultat du push sont consignés dans le compte rendu final de la mission ; ce rapport ne constitue pas à lui seul une preuve de publication.

**Verdict : DOCUMENTATION PARTIELLE.** Les quatre formats et les cas métier couvrent largement le dépôt, mais l'exhaustivité opérationnelle, la validation par chaque profil sur le site réel et la fidélité typographique DOCX→PDF restent à établir. Une validation institutionnelle est indispensable avant diffusion comme référence officielle.
