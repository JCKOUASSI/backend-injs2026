"""Observation du moteur d'habilitation (unité U2, règle R3).

Modes d'emploi :

* ``observations_habilitations``             affiche la synthèse des écarts ;
* ``observations_habilitations --campagne``  évalue hors-ligne les comptes
  gouvernés sur le référentiel chargé (sans rien changer aux réponses) ;
* ``observations_habilitations --remettre-a-zero`` vide les compteurs.

La commande sort toujours 0 : l'observation ne bloque jamais. En U2, le
référentiel est vide (U3) et les comptes ne sont pas gouvernés (U8) : la
campagne est donc explicitement sans objet, mais le mécanisme est complet.
"""
from django.core.management.base import BaseCommand

from habilitations.services import observation
from habilitations.services.moteur import mode_moteur


class Command(BaseCommand):
    help = "Synthèse du mode observation du moteur d'habilitation."

    def add_arguments(self, parser):
        parser.add_argument(
            '--campagne', action='store_true',
            help="Évalue hors-ligne tous les comptes gouvernés sur le référentiel.",
        )
        parser.add_argument(
            '--remettre-a-zero', action='store_true',
            help="Vide les compteurs d'observation du cache.",
        )

    def handle(self, *args, **options):
        mode = mode_moteur()
        self.stdout.write(f"Mode du moteur : {mode}")
        if mode == observation.MODE_OFF:
            self.stdout.write(self.style.WARNING(
                "Dispositif à l'arrêt (HABILITATIONS_OBSERVATION et "
                "HABILITATIONS_APPLICATION éteints) : aucune donnée."
            ))

        if options['remettre_a_zero']:
            observation.remettre_a_zero()
            self.stdout.write(self.style.SUCCESS(
                "Compteurs d'observation remis à zéro."
            ))
            return

        if options['campagne']:
            self._campagne()
            return

        synthese = observation.synthese_pour_api()
        etat = synthese['observations']
        self.stdout.write(
            f"Évaluations enregistrées : {etat['evaluations_total']}"
        )
        self.stdout.write(
            f"  dont comptes non gouvernés (ancien dispositif) : "
            f"{etat['non_gouvernees']}"
        )
        self.stdout.write(
            f"  autorisées par le moteur : {etat['autorisees_moteur']}"
        )
        self.stdout.write(
            f"  refusées par le moteur : {etat['refusees_moteur']}"
        )
        self.stdout.write(f"Écarts constatés : {etat['ecarts_total']}")
        self.stdout.write(
            f"  legacy autorise / moteur refuse (risque S1) : "
            f"{etat['ecarts_legacy_autorise_moteur_refuse']}"
        )
        self.stdout.write(
            f"  legacy refuse / moteur autorise (risque S2) : "
            f"{etat['ecarts_legacy_refuse_moteur_autorise']}"
        )
        if etat['motifs']:
            self.stdout.write("Motifs de refus relevés :")
            for code, nombre in sorted(
                etat['motifs'].items(), key=lambda x: (-x[1], x[0])
            ):
                self.stdout.write(f"  - {code}: {nombre}")
        if etat['premiere_observation']:
            self.stdout.write(
                f"Période couverte : {etat['premiere_observation']} → "
                f"{etat['derniere_observation']}"
            )

    def _campagne(self):
        resultat = observation.executer_campagne()
        self.stdout.write(self.style.MIGRATE_HEADING(
            "Campagne d'évaluation hors-ligne"
        ))
        self.stdout.write(
            f"Comptes gouvernés : {resultat['comptes_gouverves']}"
        )
        self.stdout.write(
            f"Permissions au référentiel : {resultat['permissions_reference']}"
        )
        self.stdout.write(
            f"Évaluations jouées : {resultat['evaluations']}"
        )
        self.stdout.write(
            f"Refus significatifs : {resultat['refus_significatifs']}"
        )
        if resultat['comptes_gouverves'] == 0:
            self.stdout.write(self.style.WARNING(
                "Aucun compte n'est encore gouverné par le nouveau dispositif "
                "(migration des comptes en U8) : campagne sans objet pour "
                "l'instant."
            ))
        elif resultat['permissions_reference'] == 0:
            self.stdout.write(self.style.WARNING(
                "Le référentiel des permissions est vide (peuplement en U3) : "
                "campagne sans objet pour l'instant."
            ))
        for code, nombre in sorted(resultat['motifs'].items()):
            self.stdout.write(f"  - {code}: {nombre}")
        for compte, permissions in resultat['comptes_avec_refus'].items():
            self.stdout.write(
                f"  compte {compte}: {', '.join(sorted(permissions))}"
            )
