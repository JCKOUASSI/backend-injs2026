# Manuel Utilisateur INJS LMD 2026

**Édition documentaire 2.0 avec réserves — 15 novembre 2026.**

Guide de formation et de continuité de service pour l'INJS d'Abidjan. Sources : dépôt `JCKOUASSI/backend-injs2026`, menu React (`frontend/src/menu/arborescence.js`), `authentication/role_groups.py`, catalogue des habilitations, applications Django et corpus du manuel antérieur du 9 novembre 2026 (`arena/documentation/manuel_utilisateur/sources/`). Cette édition **ne valide pas** l'interface authentifiée du site public ni chaque permission API par ressource ; consulter les réserves au début et à la fin du manuel.

| Fichier | Usage |
| --- | --- |
| `Manuel_Utilisateur_INJS_LMD_2026.docx` | Document éditable avec styles de titres, sommaire Word à actualiser, tableaux, images et pagination. |
| `Manuel_Utilisateur_INJS_LMD_2026.pdf` | Diffusion A4 ; mêmes contenus que le DOCX, sommaire à liens internes. Génération depuis la même source, sans conversion binaire Word : la mise en page diffère. |
| `Manuel_Utilisateur_INJS_LMD_2026.xlsx` | Outil de suivi : 15 feuilles filtrables (cartographie, profils, droits indicatifs, procédures, contrôles, cas, limites, etc.). |
| `Manuel_Utilisateur_INJS_LMD_2026.html` | Consultation hors ligne autonome : CSS, JavaScript et captures intégrés ; recherche, liens, navigation mobile, impression. |
| `RAPPORT_PRODUCTION_MANUEL.md` | Inventaire, contrôles de qualité et réserves. |

## Utilisation et actualisation

- Ouvrir le HTML dans un navigateur sans serveur. Utiliser la recherche et le sommaire latéral ; imprimer depuis le navigateur si nécessaire.
- Dans Word, ouvrir le DOCX, puis **clic droit sur le sommaire → Mettre à jour les champs** pour générer sa pagination selon l'installation locale ; vérifier l'index et les tableaux avant diffusion.
- Filtrer le XLSX par module et profil. « Conditionnel » n'est **jamais** une permission effectivement accordée à un utilisateur : vérifier la réponse des API et le périmètre.
- Après toute évolution fonctionnelle, relire le code du module et ses tests, mettre à jour les cas et les limites dans `scripts/produire_manuel_injs_2026.py`, vérifier le corpus historique, puis exécuter depuis la racine : `backend/.venv/bin/python scripts/produire_manuel_injs_2026.py` (dépendances : `python-docx`, `openpyxl`, `reportlab`, `Pillow`). Les quatre fichiers sont régénérés ensemble. Relancer les contrôles décrits dans le rapport.
- Ne pas publier de capture avec secret, jeton, cookie, matricule réel ou donnée personnelle. Les exemples et les profils de formation sont fictifs.

**Statut : DOCUMENTATION PARTIELLE** — couverture large du code et des routes, mais recette métier par compte réel et fidélité de rendu DOCX→PDF non validées sur la production. N'utiliser une procédure sensible qu'après validation par le responsable concerné.
