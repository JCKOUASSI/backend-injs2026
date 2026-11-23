"""Jeu de données de RECETTE du parcours Évaluation → Délibération → Décision.

La base de développement était vide de données métier (aucune note, aucune
inscription, aucune session de jury) : impossible de valider manuellement les
processus de bout en bout. Cette commande comble ce manque **sans jamais
toucher aux données existantes**.

Garanties :
- **idempotente** : peut être relancée sans dupliquer (get_or_create partout) ;
- **non destructive** : ne modifie ni ne supprime aucune donnée préexistante ;
- **100 % fictive** : préfixe ``RECETTE`` sur tous les matricules et
  identifiants, aucun nom de personne réelle ;
- **reproductible** : exécutable sur une base vide comme sur la base de dev.

Parcours couvert :
    Formation → Parcours → Promotion → Groupe → Maquette → UE → ECUE
    → Participant → Inscription → Note → Session de jury → Proposition
    → Décision → Résultat

Usage :
    python manage.py creer_dataset_recette_jury
    python manage.py creer_dataset_recette_jury --participants 12 --etablit
"""
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from formations.models import (
    Formation,
    Module,
    ModuleParticipant,
    NoteModule,
    NoteModuleColonne,
    Participant,
    RefFormation,
    RefModule,
)
from scolarite.models import (
    AnneeAcademique,
    DossierEtudiant,
    ECUE,
    Groupe,
    InscriptionAdministrative,
    InscriptionPedagogique,
    Maquette,
    Niveau,
    Parcours,
    Semestre,
    UE,
)

from jurys.models import MembreJury, SessionJury

PREFIXE = 'RECETTE'


class Command(BaseCommand):
    help = 'Crée un jeu de données fictif pour valider le parcours de délibération.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--participants', type=int, default=10,
            help='Nombre de participants à inscrire (défaut : 10).',
        )
        parser.add_argument(
            '--etablit', action='store_true',
            help="Lance en plus le calcul des propositions du jury.",
        )

    def handle(self, *args, **options):
        n = options['participants']
        aujourd_hui = timezone.localdate()
# ── Référentiels académiques ────────────────────────────────────
        annee, _ = AnneeAcademique.objects.get_or_create(
            libelle='2026-2027',
            defaults={
                'date_debut': aujourd_hui - timedelta(days=60),
                'date_fin': aujourd_hui + timedelta(days=300),
                'courante': True,
            },
        )
        ref_formation, _ = RefFormation.objects.get_or_create(
            intitule=f'{PREFIXE} — Licence LMD',
        )
        niveau, _ = Niveau.objects.get_or_create(
            code='REC1',
            defaults={'libelle': f'{PREFIXE} Licence 1', 'credits_requis': 60},
        )
        parcours, _ = Parcours.objects.get_or_create(
            ref_formation=ref_formation, intitule=f'{PREFIXE} — Parcours A',
        )
        # Le modèle `Groupe` se rattache directement à (année, formation, niveau) :
        # le dépôt n'a pas d'entité `Promotion` intermédiaire — on respecte le
        # modèle réel plutôt que d'introduire un vocabulaire parallèle.
        groupe, _ = Groupe.objects.get_or_create(
            annee_academique=annee, ref_formation=ref_formation, niveau=niveau,
            nom=f'{PREFIXE}-G1', defaults={'parcours': parcours, 'actif': True},
        )
        semestre, _ = Semestre.objects.get_or_create(niveau=niveau, numero=1)

        # ── Maquette → UE → ECUE ────────────────────────────────────────
        maquette = Maquette.objects.filter(
            annee_academique=annee, ref_formation=ref_formation, niveau=niveau,
        ).first()
        if maquette is None:
            maquette = Maquette.objects.create(
                annee_academique=annee, ref_formation=ref_formation, niveau=niveau,
                statut=Maquette.Statut.BROUILLON,
            )
            ue = UE.objects.create(
                maquette=maquette, semestre=semestre,
                code=f'{PREFIXE}-UE1', credits=30,
            )
            self._ecues(ue)
            # La maquette ACTIVE devient immuable : on l'active en dernier.
            maquette.statut = Maquette.Statut.ACTIVE
            maquette.save(update_fields=['statut'])

        formation_op, _ = Formation.objects.get_or_create(
            formation=f'{PREFIXE} — Licence op',
        )

        # ── Participants + inscriptions + notes ─────────────────────────
        self._participants(n, annee, ref_formation, niveau, formation_op, parcours)
# ── Session de jury ─────────────────────────────────────────────
        from django.contrib.auth import get_user_model
        User = get_user_model()
        dfrc = User.objects.filter(
            role__in=('INJS_ADMIN', 'ADMIN', 'CHEF_INJS_ADMIN'),
        ).first()
        if dfrc is None:
            self.stdout.write(self.style.WARNING(
                'Aucun compte DFRC/ADMIN : session de jury non créée. '
                'Créez un compte administrateur puis relancez la commande.',
            ))
            return
        session, cree = SessionJury.objects.get_or_create(
            annee_academique=annee, ref_formation=ref_formation, niveau=niveau,
            maquette=maquette, parcours=parcours,
            defaults={'libelle': f'{PREFIXE} — Jury L1 2026-2027', 'creee_par': dfrc},
        )
        if cree:
            self.stdout.write(self.style.SUCCESS(f'Session de jury #{session.pk} créée.'))
        MembreJury.objects.get_or_create(
            session=session, user=dfrc,
            defaults={'fonction': MembreJury.Fonction.PRESIDENT, 'ajoute_par': dfrc},
        )

        if options['etablit']:
            from jurys import services
            services.calculer_propositions(session, dfrc)
            self.stdout.write(self.style.SUCCESS('Propositions calculées.'))

        self.stdout.write(self.style.SUCCESS(
            f'Jeu de recette prêt : {n} participants, session #{session.pk}.'
        ))

    def _ecues(self, ue):
        """Deux ECUE (10 ECTS chacun) rattachés à l'UE."""
        for index, code in enumerate(('ECUE-A', 'ECUE-B'), start=1):
            ref_module, _ = RefModule.objects.get_or_create(
                intitule=f'{PREFIXE} — Module {index}',
            )
            ECUE.objects.get_or_create(
                ue=ue, code=f'{PREFIXE}-{code}',
                defaults={
                    'intitule': f'{PREFIXE} — {code}', 'credits': 10,
                    'ref_module': ref_module,
                },
            )

    def _participants(self, n, annee, ref_formation, niveau, formation_op, parcours=None):
        """Participants, inscriptions administratives et pédagogiques + notes."""
        maquette = Maquette.objects.filter(
            annee_academique=annee, ref_formation=ref_formation, niveau=niveau,
        ).first()
        for index in range(1, n + 1):
            matricule = f'{PREFIXE}-{index:03d}'
            participant, cree = Participant.objects.get_or_create(
                matricule=matricule,
                defaults={
                    'nom': PREFIXE, 'prenom': f'Participant {index:03d}', 'grade': 'L1',
                },
            )
            if not cree:
                continue
            dossier, _ = DossierEtudiant.objects.get_or_create(participant=participant)
            inscription, _ = InscriptionAdministrative.objects.get_or_create(
                etudiant=dossier, annee_academique=annee,
                ref_formation=ref_formation, niveau=niveau,
                statut=InscriptionAdministrative.Statut.VALIDEE,
                # `services.inscriptions_concernees()` filtre sur le parcours
                # quand la session en a un : sans ce rattachement, la
                # population de la session serait vide et le moteur ne
                # produirait aucune proposition.
                defaults={'parcours': parcours} if parcours else {},
            )
            self._inscription_pedagogique(inscription, participant, maquette, formation_op)
            self._note(inscription, participant, maquette, formation_op)

    def _inscription_pedagogique(self, inscription, participant, maquette, formation_op):
        if maquette is None:
            return
        for ue in maquette.unites_enseignement.all():
            for ecue in ue.ecues.all():
                module, _ = Module.objects.get_or_create(
                    formation=formation_op, intitule=ecue.code,
                    defaults={'ref_module': ecue.ref_module},
                )
                mp, _ = ModuleParticipant.objects.get_or_create(
                    module=module, participant=participant,
                )
                InscriptionPedagogique.objects.get_or_create(
                    inscription=inscription, ecue=ecue,
                    defaults={
                        'module_participant': mp,
                        # `semestre` est NOT NULL : on le déduit de l'ECUE.
                        'semestre': ecue.ue.semestre,
                        'statut': InscriptionPedagogique.Statut.VALIDEE,
                    },
                )

    def _note(self, inscription, participant, maquette, formation_op):
        """Note valide et verrouillée : le moteur ECTS l'exige pour calculer."""
        if maquette is None:
            return
        for ue in maquette.unites_enseignement.all():
            for ecue in ue.ecues.all():
                module = Module.objects.filter(
                    formation=formation_op, intitule=ecue.code,
                ).first()
                if module is None:
                    continue
                colonne, _ = NoteModuleColonne.objects.get_or_create(
                    module=module, libelle='Note finale', defaults={'note_max': 20},
                )
                # Moyenne 14/20 : l'étudiant valide le semestre.
                NoteModule.objects.get_or_create(
                    colonne=colonne, participant=participant,
                    defaults={
                        'note': Decimal('14.00'), 'verrouillee': True,
                        'statut_validation': 'VALIDEE',
                    },
                )
