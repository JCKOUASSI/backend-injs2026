# Contrat transversal des données créées dans INJS

Décision utilisateur : toute entité que l'application permet de créer doit pouvoir être visualisée, modifiée, supprimée (si non utilisée), archivée (si utilisée), exportée en DOCX/XLSX/CSV/PDF et importée en XLSX/CSV. Les listes doivent proposer une sélection par cases à cocher pour les actions groupées de validation/enregistrement, activation/désactivation, suppression et archivage.

## Règle de conservation

- La suppression définitive n'est autorisée que si aucune relation métier, y compris cachée ou archivée, ne dépend de la ligne. Aucune suppression en cascade de dossiers, notes, pièces ou historiques ; aucune déliaison silencieuse (SET_NULL).
- Si la ligne est utilisée, conserver la ligne et ses relations ; archiver si le modèle le permet, sinon désactiver si le modèle dispose d'un état actif. Si aucun état de retrait n'existe, refuser explicitement l'opération. Ne jamais présenter une désactivation comme un archivage.
- Maintenir les autorisations, la journalisation, une confirmation explicite et des tests des refus ; ne pas utiliser la base VPS pour les tests destructifs.
- Un import doit valider l'ensemble du fichier avant toute modification et produire un bilan d'erreurs ; pas de réécriture silencieuse des identifiants, statuts ou calendriers.
- Une action groupée doit recontrôler les droits et les dépendances au serveur ; sélection à portée clairement indiquée (page/filtre/tout) et résultat explicite pour chaque ligne. Préférer l'atomicité par lot à un ensemble de requêtes indépendantes.

## Progression (ne pas assimiler ce lot à une couverture globale)

1. Hub Référentiels : les trois plaquettes de l'offre disposent déjà du CRUD, d'exports DOCX/XLSX/CSV/PDF et d'imports XLSX/CSV (tests existants). Premier lot en branche : DELETE contrôlé pour les référentiels du registre, avec conservation des lignes liées et journalisation ; frontend explicite la différence entre suppression, archivage et désactivation. **Pas encore déployé sur le VPS.**
2. Hub Référentiels : sélection multiple et actions groupées, contrôle serveur atomique, tests d'autorisations et de dépendances ; compléter la gestion des imports/exports pour les autres entrées du registre.
3. Étudiants / Admissions / Scolarité, puis autres modules : inventaire par entité de la création, lecture, édition, états métier, liens, imports/exports et actions groupées ; appliquer le contrat en respectant les cycles de vie et la traçabilité. Un dossier validé, une note publiée ou une pièce jointe ne doivent pas être effacés par une action générique.

Le site public peut rester sur les images précédentes tant que les lots ne sont pas validés et déployés séparément avec sauvegarde et possibilité de retour arrière. Aucune migration ni modification de données VPS n'est requise par le premier lot de code.
