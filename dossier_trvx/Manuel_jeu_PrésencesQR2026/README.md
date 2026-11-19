# Manuel démo de recette de bout en bout — Présences QR (2026)

- [DOCX éditable](Manuel_Demo_Recette_Presences_QR_2026.docx)
- [PDF de diffusion](Manuel_Demo_Recette_Presences_QR_2026.pdf)

**Protocole non exécuté :** 85 scénarios en dix chapitres. Aucun résultat, justificatif ni visa n’est prérempli. Les deux formats proviennent de la même source `scripts/produire_manuel_demo_presencesqr_2026.py` et couvrent la chaîne EDT → séance → QR → badgeage web/Flutter → heartbeat/sortie → émargement manuel/clôture → registre/audit/statistiques, ainsi que les refus, les droits, la géofence, la concurrence et le canal legacy. Un inventaire fini ne garantit pas littéralement *tous* les états ou futurs changements ; compléter la recette avec les responsables métiers.

À utiliser seulement dans un environnement de recette autorisé et isolé avec données fictives, appareils et sites d’essai. **Ne pas générer de données fictives ou effectuer des tests intrusifs en production.** Garder les preuves expurgées hors des documents et éviter de copier tokens QR, secrets, coordonnées brutes et identités réelles. Un QR scanné n’est pas, à lui seul, une preuve de présence physique ; sans site géolocalisé exploitable le contrôle peut être permissif. L’année complète GET INJS APP et les appareils réels ne sont pas considérés validés par les anciennes campagnes automatisées citées.

Pour régénérer une trame vierge depuis la racine : `backend/.venv/bin/python scripts/produire_manuel_demo_presencesqr_2026.py` (dépendances `python-docx`, `reportlab`, police DejaVu Sans). **Ne pas écraser une copie de recette déjà renseignée ou signée.** Le PDF est composé depuis les mêmes textes que le DOCX, sans conversion par Word : pagination indépendante. Cette livraison n’a ni exécuté de recette authentifiée, ni touché à la production.
