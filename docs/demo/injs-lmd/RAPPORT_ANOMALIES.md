# Anomalies et limites restantes

## Corrections appliquées

- Le contrôle de `seed_plateforme_demo` attendait des totaux figés (531 UE/779 ECUE) incompatibles avec les sources présentes. Il vérifie maintenant des seuils de couverture et les invariants exacts de la cohorte; le seed complet a été rejoué sans doublon et avec calendrier inchangé.
- Le seeder central omettait GET INJS. Il appelle maintenant le seeder existant en mode sans import secondaire et vérifie la présence d’EDT publiés, de placements et de séances.
- Le document de conception GET INJS n’était pas monté dans le conteneur backend. Une copie embarquée avec le paquet Django est maintenant le dernier chemin de repli; le test ne dépend plus de la profondeur du montage Docker.
- Les modules/écrans lourds sont chargés à la demande; le bundle principal a été réduit et redéployé.
- La suite frontend complète a découvert une affectation non déclarée `basculerTout` dans l’écran Maquettes. La fonction est déclarée correctement; les 23 tests de cet écran puis les 2 256 tests frontend passent.

## Limites observées

- Aucun pointage QR n’a été injecté dans la base de démonstration. Les séances sont disponibles et les règles de scan QR sont testées; la démonstration réelle de pointage demande une occurrence dans sa fenêtre horaire.
- Une exécution détenue par un autre worker pouvait être déclarée orpheline à tort sur les plateformes sans `/proc`. La détection utilise désormais les `native_id` des threads Python actifs et consulte `/proc` sur Linux. Validation PostgreSQL : 6 tests ciblés et 788 tests EDT/Présences réussis; la base de test dédiée a été supprimée après exécution.
- `check --deploy` signale une configuration candidate non-production : `DEBUG=True`, secret Django insuffisamment robuste, paramètres TLS/HSTS et cookies sécurisés non configurés. Ces valeurs ne doivent être durcies qu’avec le nom d’hôte/TLS et les secrets du déploiement connus; activer une redirection HTTPS sur les ports HTTP locaux casserait l’aperçu.
- La revue automatique avait initialement refusé l’export nominatif. Après approbation explicite de l’utilisateur, le classeur inclut les noms, prénoms, matricules, sexe, emails DEMO, groupes et inscriptions de la cohorte fictive générée par `seed_candidatures_demo`. Les téléphones, dates/lieux de naissance, coordonnées, données hors cohorte et secrets QR restent exclus.
