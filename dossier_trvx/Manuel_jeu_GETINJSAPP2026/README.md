# Manuel démo de recette — GET INJS APP (2026)

- [`Manuel_Demo_Recette_GET_INJS_APP_2026.docx`](Manuel_Demo_Recette_GET_INJS_APP_2026.docx) — version éditable, destinée à la saisie des constats et aux visas.
- [`Manuel_Demo_Recette_GET_INJS_APP_2026.pdf`](Manuel_Demo_Recette_GET_INJS_APP_2026.pdf) — version de diffusion, générée depuis la même source que le DOCX.

**Statut : protocole non exécuté.** 71 scénarios, neuf chapitres couvrant l’accès et les droits, les référentiels LMD, l’import et la population, le dimensionnement, les générations manuelle et automatique, les campagnes/versions/publication, la grille et les exports, l’interopérabilité Présences/QR et les contrôles transversaux. Chaque scénario indique procédure, résultat attendu, profil, preuve et source technique ; tous les constats et visas sont vierges. L’exhaustivité absolue de tous les états futurs n’est pas garantie : enrichir la matrice lors des évolutions.

## Usage responsable

Exécuter exclusivement sur un environnement de recette autorisé et isolé, avec comptes habilités et jeu fictif. Ne pas injecter de données de démo en production. Documenter l’année et les semaines S1/S2 officiellement approuvées : en leur absence, une année complète ne peut pas être considérée validée. Conserver les preuves expurgées hors de ce dossier et appliquer la procédure institutionnelle de signature. L’inventaire du code et les tests automatisés cités ne sont pas des résultats de recette métier authentifiée.

Le projet de gestion GET INJS APP décrit ici est **l’interface React** (`frontend/src/pages/getinjs/` et `Edts.jsx`) avec backend Django ; l’application Flutter du dépôt concerne surtout le badgeage mobile/QR et l’interopérabilité aval, et ne remplace pas l’écran web de génération.

Génération documentaire : `backend/.venv/bin/python scripts/produire_manuel_demo_getinjs_2026.py` depuis la racine (dépendances `python-docx`, `reportlab`, police DejaVu Sans). **Attention :** relancer le script régénère et remplace les deux modèles documentaires ; conserver séparément les exemplaires de recette déjà renseignés et signés. Le PDF est composé directement à partir des mêmes textes, pas converti du DOCX : sa pagination peut différer. Aucun déploiement ni test de l’interface en production n’a été effectué pour cette livraison.
