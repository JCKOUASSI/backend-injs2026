"""Appliquer une politique de contraintes souples, de façon reproductible.

Pourquoi une commande alors qu'il existe un écran d'administration. L'écran
règle **l'environnement où il est ouvert** ; il ne transporte pas la décision
vers la préproduction ou la production, et il ne laisse pas de trace
versionnable. Cette commande permet de rejouer exactement la même décision,
avec son motif, sur n'importe quelle base — et de la vérifier avant de
l'appliquer (`--verifier`).

Trois règles de conduite :

1. **aucune écriture sans motif** : une politique sans justification n'est pas
   une décision, c'est un réglage anonyme. `--motif` est obligatoire dès que la
   commande écrit ;
2. **validation avant écriture** : les bornes passent par `full_clean()` du
   modèle, donc une pause inversée ou une borne nulle échoue avec le même
   message que dans l'admin ;
3. **idempotence** : rejouer la même politique ne modifie ni la date ni
   l'auteur de la décision — relancer un déploiement ne doit pas réécrire
   l'historique.

Exemples
--------
    python manage.py regler_contraintes_souples --verifier
    python manage.py regler_contraintes_souples \\
        --activer --max-consecutives 4 --max-jour 8 \\
        --motif "Bornes du référentiel (doc 2, §11 K) appliquées."

    python manage.py regler_contraintes_souples --desactiver \\
        --motif "Retour au comportement par défaut après la rentrée."
"""

from datetime import time

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from edts.models import PolitiqueContraintesSouples
from edts.moteur import contraintes as C


class Command(BaseCommand):
    help = (
        'Enregistre la politique des contraintes souples (bornes, pause, poids) '
        'avec son motif. Aucune écriture sans --motif.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--activer', action='store_true',
            help='Active les règles souples (pénalités uniquement, jamais de refus).',
        )
        parser.add_argument(
            '--desactiver', action='store_true',
            help='Désactive les règles souples en conservant les bornes enregistrées.',
        )
        parser.add_argument(
            '--max-consecutives', dest='max_consecutives', type=float, default=None,
            help='Série de cours continue maximale, en heures (ex. 4).',
        )
        parser.add_argument(
            '--max-jour', dest='max_jour', type=float, default=None,
            help='Total de cours maximal par journée de groupe, en heures (ex. 8).',
        )
        parser.add_argument(
            '--tolerance', type=int, default=None,
            help='Interruption tolérée entre deux séances, en minutes (ex. 15).',
        )
        parser.add_argument(
            '--pause', default=None,
            help='Pause institutionnelle « HH:MM-HH:MM » (ex. 11:45-13:30). '
                 'Sans cette option, aucune pause n’est déclarée.',
        )
        parser.add_argument(
            '--poids-trou', dest='poids_trou', type=int, default=None,
        )
        parser.add_argument(
            '--poids-consecutif', dest='poids_consecutif', type=int, default=None,
        )
        parser.add_argument(
            '--poids-surcharge', dest='poids_surcharge', type=int, default=None,
        )
        parser.add_argument(
            '--sans-pause', dest='sans_pause', action='store_true',
            help='Ne déclare aucune pause institutionnelle (efface celle qui '
                 'serait enregistrée).',
        )
        parser.add_argument(
            '--motif', default='',
            help='Pourquoi cette décision. Obligatoire dès que la commande écrit.',
        )
        parser.add_argument(
            '--auteur', default='',
            help='Identifiant du compte qui porte la décision (facultatif).',
        )
        parser.add_argument(
            '--verifier', action='store_true',
            help='N’écrit rien : affiche la politique effective et les valeurs demandées.',
        )

    # ── Aides ────────────────────────────────────────────────────────────────
    def _pause_demandee(self, valeur):
        """« 11:45-13:30 » → ('11:45', '13:30'), validé par le moteur."""
        if valeur is None:
            return None
        morceaux = valeur.split('-')
        if len(morceaux) != 2 or not all(morceaux):
            raise CommandError(
                'Format de pause invalide : attendu « HH:MM-HH:MM » '
                f'(reçu : {valeur!r}).')
        return (morceaux[0].strip(), morceaux[1].strip())

    def _valeurs_demandees(self, options):
        valeurs = {}
        if options['activer'] and options['desactiver']:
            raise CommandError('Choisissez --activer OU --desactiver, pas les deux.')
        if options['activer']:
            valeurs['actives'] = True
        if options['desactiver']:
            valeurs['actives'] = False
        correspondances = {
            'max_consecutives': 'max_heures_consecutives',
            'max_jour': 'max_heures_par_jour',
            'tolerance': 'tolerance_minutes',
            'poids_trou': 'poids_trou',
            'poids_consecutif': 'poids_consecutif',
            'poids_surcharge': 'poids_surcharge',
        }
        for option, champ in correspondances.items():
            if options[option] is not None:
                valeurs[champ] = options[option]
        if options['pause'] is not None and options['sans_pause']:
            raise CommandError('Choisissez --pause OU --sans-pause, pas les deux.')
        if options['sans_pause']:
            valeurs['pause_dejeuner'] = None
        elif options['pause'] is not None:
            valeurs['pause_dejeuner'] = self._pause_demandee(options['pause'])
        return valeurs

    @staticmethod
    def _decrire(politique):
        # Toujours via la forme lisible : « pause 735 – 810 » ne veut rien dire
        # pour un être humain, et c'est exactement le défaut corrigé dans l'API.
        lisible = C.politique_lisible(politique)
        pause = lisible.get('pause_dejeuner')
        if isinstance(pause, (list, tuple)):
            pause = f'{pause[0]} – {pause[1]}'
        return (
            f"actives={politique['actives']}, "
            f"{politique['max_heures_consecutives']:g} h consécutives, "
            f"{politique['max_heures_par_jour']:g} h/jour, "
            f"tolérance {politique['tolerance_minutes']} min, "
            f"pause {pause or 'aucune'}, "
            f"poids {politique['poids_trou']}/{politique['poids_consecutif']}/"
            f"{politique['poids_surcharge']}"
        )

    # ── Commande ─────────────────────────────────────────────────────────────
    def handle(self, *args, **options):
        self.effective = C.politique_effective()
        valeurs = self._valeurs_demandees(options)

        self.stdout.write('Politique effective avant :')
        self.stdout.write(f'  origine {self.effective["origine"]} — '
                          f'{self._decrire(self.effective["politique"])}')

        if options['verifier']:
            if valeurs:
                self.stdout.write('Valeurs demandées (non écrites) :')
                for cle, valeur in valeurs.items():
                    self.stdout.write(f'  {cle} = {valeur}')
            self.stdout.write(self.style.WARNING('Aucune écriture (--verifier).'))
            return

        if not valeurs:
            raise CommandError(
                'Aucune valeur à enregistrer : précisez au moins --activer ou '
                '--desactiver, ou une borne.')
        if not options['motif'].strip():
            raise CommandError(
                'Un motif est obligatoire : une politique sans justification '
                'n’est pas une décision traçable. Utilisez --motif « … ».')

        ligne = PolitiqueContraintesSouples.charger() or PolitiqueContraintesSouples()
        if options['auteur']:
            utilisateur = get_user_model().objects.filter(
                username=options['auteur']).first()
            if utilisateur is None:
                raise CommandError(
                    f'Compte inconnu : {options["auteur"]!r}.')
            ligne.modifie_par = utilisateur
        ligne.motif = options['motif'].strip()
        for champ, valeur in valeurs.items():
            if champ == 'pause_dejeuner':
                # Le modèle porte deux champs (début/fin) ; la politique les
                # exprime en un couple. La conversion se fait ici, jamais par
                # un attribut fantôme que Django ignorerait au moment du save.
                if valeur is None:
                    ligne.pause_debut = None
                    ligne.pause_fin = None
                    continue
                try:
                    ligne.pause_debut = time.fromisoformat(valeur[0])
                    ligne.pause_fin = time.fromisoformat(valeur[1])
                except ValueError:
                    raise CommandError(
                        'Horaire de pause invalide : attendu « HH:MM » '
                        f'(reçu : {valeur!r}).') from None
                continue
            setattr(ligne, champ, valeur)

        # Validation AVANT toute écriture : mêmes règles que l'admin.
        try:
            ligne.full_clean()
        except ValidationError as erreur:
            details = '; '.join(
                f'{champ} : {" ".join(messages)}'
                for champ, messages in erreur.message_dict.items()
            )
            raise CommandError(f'Politique refusée — {details}') from None

        existe = ligne.pk is not None and PolitiqueContraintesSouples.objects.filter(
            pk=1).exists()
        if existe and self._est_identique(ligne):
            self.stdout.write(self.style.SUCCESS(
                'Politique déjà enregistrée à l’identique : rien n’a été modifié '
                '(ni date, ni auteur).'))
            return

        ligne.save()
        apres = C.politique_effective()
        self.stdout.write(self.style.SUCCESS(
            f'Politique enregistrée (origine {apres["origine"]}) — '
            f'{self._decrire(apres["politique"])}'))
        self.stdout.write(f'  motif : {ligne.motif}')
        if ligne.modifie_par_id:
            self.stdout.write(f'  auteur : {ligne.modifie_par.get_username()}')
        self.stdout.write(
            '  Rappel : ces règles produisent des pénalités, jamais des refus.')

    def _est_identique(self, ligne):
        """Vrai si la ligne enregistrée porte déjà exactement ces valeurs."""
        actuelle = PolitiqueContraintesSouples.charger()
        if actuelle is None:
            return False
        try:
            actuelle.full_clean()
        except ValidationError:
            return False
        return (
            actuelle.en_politique() == ligne.en_politique()
            and (actuelle.motif or '') == (ligne.motif or '')
            and actuelle.modifie_par_id == ligne.modifie_par_id
        )
