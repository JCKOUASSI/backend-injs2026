# Guide de remise à zéro DEMO

Aucune remise à zéro globale de la plateforme n’est fournie ni utilisée. La commande centrale est additive et idempotente; elle préserve les comptes existants, les données institutionnelles et le calendrier.

Le seeder autonome `donnees_demonstration_getinjs --supprimer` ne supprime que ses objets explicitement marqués `DEMO-…`; il ne retire pas les données créées par les autres seeds et n’est pas un reset complet. Ne l’exécuter que si ce jeu isolé est la cible et après vérification des dépendances.

Pour restaurer l’état antérieur du remplissage du 20 novembre 2026, la sauvegarde vérifiée est conservée hors dépôt à `/private/tmp/injs-demo-preseed-20261120.sqlite3`. Une restauration remplace la base candidate et doit être planifiée hors des requêtes actives; elle n’a pas été exécutée.
