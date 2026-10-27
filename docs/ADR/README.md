# Registre des décisions d'architecture (ADR)

Chaque décision sensible est consignée au format **Contexte / Décision / Conséquences /
Alternatives rejetées**. Les décisions d'architecture générales imposées au projet
(DA-01 → DA-12) sont rappelées dans [../ARCHITECTURE.md](../ARCHITECTURE.md).

| ADR | Titre | Décision liée |
|-----|-------|---------------|
| [ADR-001](ADR-001-doubles-representations-D1-D5.md) | Traitement des doubles représentations D1 à D5 | DA-02 |
| [ADR-002](ADR-002-deux-finances-jamais-fusionnees.md) | Deux domaines financiers distincts, jamais fusionnés | DA-07 |
| [ADR-003](ADR-003-edt-externe-et-moteur-natif-complementaires.md) | Emploi du temps : contrat externe conservé, moteur natif complémentaire | DA-09 |
| [ADR-004](ADR-004-middlewares-demo-iframe-gardes-debug.md) | Aides de démonstration en iframe gardées par `DEBUG` + variable d'environnement | Sécurité de démo |
| [ADR-005](ADR-005-conservation-arborescence-django-a-plat.md) | Arborescence Django à plat et noms techniques hérités conservés | DA-01 / DA-12 |
| [ADR-006](ADR-006-unicite-libelles-insensible-casse.md) | Anti-doublon de libellé insensible à la casse/accents, portable SQLite et PostgreSQL (implémentation LOT 1) | DA-02 |
| [ADR-007](ADR-007-generation-coordonnee-edt-injs.md) | Génération des EDT INJS : orchestration séquentielle déterministe, périmètre dérivé des données | DA-09 |
