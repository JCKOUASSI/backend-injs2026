"""EDT et assiduité d'exemple, rattachés à la chaîne pédagogique LMD.

Six groupes peuplés, six filières lorsque le référentiel le permet, cinq
ECUE par groupe : trente créneaux hebdomadaires. Les semaines vont du début
de l'année courante à la semaine d'aujourd'hui. Seules les occurrences
**terminées** reçoivent des pointages ; aucune présence future n'est créée.

Les relevés sont fictifs, identifiés par ``device_id='[Exemple] SEED_EDT_DEMO'``.
Leur distribution est stable (empreinte de l'ECUE, du matricule et de la date) :
78 % présents, 10 % retards, 7 % absents, 3 % absences justifiées, 2 % dispensés.
Ce scénario illustre l'application ; ce n'est ni un relevé réel ni une norme INJS.

Relancer la commande prolonge les EDT et complète l'historique sans dupliquer
ni écraser les pointages existants. ``--purger`` retire les seuls EDT signés
par ce seed et leurs dépendances. Les créneaux types sont un référentiel
partagé : ils sont réutilisés, jamais supprimés. Une présence réelle saisie
sur un EDT d'exemple bloque sa suppression (aucune perte silencieuse).
"""
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal
import hashlib

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import models, transaction
from django.db.models import Count
from django.utils import timezone

from edts.models import AffectationCreneau, CreneauTemplate, EmploiDuTemps
from edts.services import detecter_conflits
from formations.models import RefSalle
from presences.models import Pointage
from presences.seances_edt_services import est_seance_du_jour, horodatages
from scolarite.models import (
    AffectationGroupe, AffectationPedagogique, AnneeAcademique, Groupe,
    InscriptionAdministrative,
)

MARQUE = '[Exemple]'
SOURCE = f'{MARQUE} SEED_EDT_DEMO'
SIGNATURE = 'edt-demo-v1:'
JOURS = ('LUNDI', 'MARDI', 'MERCREDI', 'JEUDI', 'VENDREDI')
HORAIRES = (
    (time(6), time(7)), (time(7, 30), time(9, 30)),
    (time(9, 45), time(11, 45)), (time(13, 30), time(15, 30)),
    (time(15, 45), time(17, 45)), (time(18), time(20)),
)
NB_GROUPES = len(HORAIRES)
ECUE_PAR_GROUPE = len(JOURS)


def _heure(valeur):
    return valeur.strftime('%H:%M')


def _selection_groupes(annee):
    """Groupes reproductibles, assez d'ECUE et de membres pour la démonstration."""
    affectations = (
        AffectationPedagogique.objects.filter(
            annee_academique=annee, observations__startswith=MARQUE,
            statut=AffectationPedagogique.Statut.VALIDEE,
            groupe__actif=True, ecue__isnull=False,
            type_enseignement__in=('CM', 'TD', 'TP'),
        )
        .exclude(ecue__intitule__icontains='stage')
        .exclude(ecue__intitule__icontains='mémoire')
        .exclude(ecue__intitule__icontains='projet professionnel')
    )
    disponibles = set(
        affectations.values('groupe_id').annotate(n=Count('id'))
        .filter(n__gte=ECUE_PAR_GROUPE).values_list('groupe_id', flat=True)
    )
    groupes = (
        Groupe.objects.filter(pk__in=disponibles)
        .annotate(effectif=Count(
            'affectations__inscription__etudiant__participant',
            filter=models.Q(
                affectations__active=True,
                affectations__inscription__statut=InscriptionAdministrative.Statut.VALIDEE,
            ), distinct=True,
        ))
        .filter(effectif__gte=6, effectif__lte=32)
        .select_related('ref_formation__filiere', 'niveau')
        .order_by('ref_formation__filiere__code', 'effectif', 'pk')
    )
    choisis, vus = [], set()
    for groupe in groupes:
        cle = groupe.ref_formation.filiere_id or groupe.ref_formation_id
        if cle not in vus:
            choisis.append(groupe)
            vus.add(cle)
        if len(choisis) == NB_GROUPES:
            break
    # Si moins de six filières sont disponibles, compléter avec d'autres groupes.
    for groupe in groupes:
        if len(choisis) == NB_GROUPES:
            break
        if groupe.pk not in {g.pk for g in choisis}:
            choisis.append(groupe)
    return sorted(choisis, key=lambda g: g.pk), affectations


def _membres(groupes):
    resultat = defaultdict(set)
    for gid, pid in AffectationGroupe.objects.filter(
        groupe__in=groupes, active=True,
        inscription__statut=InscriptionAdministrative.Statut.VALIDEE,
        inscription__etudiant__participant__isnull=False,
    ).values_list('groupe_id', 'inscription__etudiant__participant_id'):
        resultat[gid].add(pid)
    return resultat


def _assiduite(ap, participant_id, matricules, jour):
    """Distribution déterministe, indépendante de l'ordre des PK et des reruns."""
    cle = f'{SOURCE}|{ap.ecue.code}|{matricules[participant_id]}|{jour.isoformat()}'
    nombre = int(hashlib.sha256(cle.encode()).hexdigest()[:12], 16) % 100
    if nombre < 78:
        return Pointage.StatutAssiduite.PRESENT
    if nombre < 88:
        return Pointage.StatutAssiduite.RETARD
    if nombre < 95:
        return Pointage.StatutAssiduite.ABSENT
    if nombre < 98:
        return Pointage.StatutAssiduite.ABSENCE_JUSTIFIEE
    return Pointage.StatutAssiduite.EXCUSE


def _pointage(ap, seance, pid, matricules, jour, debut, fin):
    assiduite = _assiduite(ap, pid, matricules, jour)
    presente = assiduite in (Pointage.StatutAssiduite.PRESENT, Pointage.StatutAssiduite.RETARD)
    entree = debut
    if assiduite == Pointage.StatutAssiduite.RETARD:
        entree += timedelta(minutes=15)
    sortie = fin if presente else entree
    statut = Pointage.Statut.TERMINE if presente else (
        Pointage.Statut.ABSENT_NON_BADGE
        if assiduite == Pointage.StatutAssiduite.ABSENT else Pointage.Statut.FORCE_DFRC
    )
    return Pointage(
        participant_id=pid, seance_edt=seance, date_journee=jour,
        timestamp_entree=entree, timestamp_sortie=sortie,
        duree_presence_minutes=Decimal(str(round((sortie - entree).total_seconds() / 60, 2))),
        statut=statut, statut_assiduite=assiduite, device_id=SOURCE,
        annee_academique_id=ap.annee_academique_id,
        groupe_lmd_id=ap.groupe_id, ecue_lmd_id=ap.ecue_id,
    )


class Command(BaseCommand):
    help = "EDT hebdomadaires et pointages passés d'exemple [Exemple], idempotents."

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Simule sans écrire.')
        parser.add_argument('--purger', action='store_true', help='Retire les seuls EDT signés par ce seed.')

    def _edts_exemple(self):
        return EmploiDuTemps.objects.filter(
            population_type='GROUPE', titre__startswith=MARQUE,
            empreinte__startswith=SIGNATURE,
        )

    def _purger(self):
        with transaction.atomic():
            edts = self._edts_exemple()
            reels = Pointage.objects.filter(seance_edt__emploi_du_temps__in=edts).exclude(device_id=SOURCE)
            if reels.exists():
                raise CommandError(
                    f'Purge annulée : {reels.count()} pointage(s) hors exemple sont rattachés '
                    'à ces EDT. Les conserver exige de ne pas supprimer leurs séances.'
                )
            nb_points = Pointage.objects.filter(seance_edt__emploi_du_temps__in=edts).count()
            nb_seances = AffectationCreneau.objects.filter(emploi_du_temps__in=edts).count()
            nb_edts = edts.count()
            edts.delete()
        self.stdout.write(self.style.SUCCESS(
            f'Purge EDT : {nb_edts} emploi(s) du temps, {nb_seances} créneaux, '
            f'{nb_points} pointages retirés. Référentiel horaire et données hors exemple conservés.'
        ))

    def handle(self, *args, **options):
        if options['purger'] and options['dry_run']:
            raise CommandError('--purger et --dry-run sont incompatibles.')
        if options['purger']:
            self._purger()
            return
        annee = AnneeAcademique.objects.filter(courante=True).first()
        if annee is None:
            raise CommandError('Aucune année académique courante.')
        now = timezone.now()
        today = timezone.localdate(now)
        dernier_jour = min(today, annee.date_fin)
        semaine_fin = max(1, (dernier_jour - annee.date_debut).days // 7 + 1)
        groupes, candidates = _selection_groupes(annee)
        if not groupes:
            raise CommandError(
                'Aucun groupe eligible : lancer seed_enseignants_demo et '
                'seed_lot1_2_inscriptions (cinq ECUE et six membres actifs minimum).'
            )
        salles = list(RefSalle.objects.filter(
            type_lieu__in=('COURS', 'AMPHI'), capacite__gte=max(g.effectif for g in groupes),
        ).order_by('nom', 'pk')[:len(groupes)])
        if len(salles) != len(groupes):
            raise CommandError('Pas assez de salles distinctes et adaptées au référentiel INJS.')
        from formations.models import Participant
        membres = _membres(groupes)
        matricules = dict(Participant.objects.filter(
            pk__in={pid for ids in membres.values() for pid in ids},
        ).values_list('pk', 'matricule'))
        createur = get_user_model().objects.filter(is_active=True, is_superuser=True).order_by('pk').first()
        nb_edts = nb_seances = nb_points = nb_conflits = 0
        with transaction.atomic():
            edts = []
            for rang, groupe in enumerate(groupes):
                signature = f'{SIGNATURE}{annee.pk}:{groupe.pk}'
                edt = EmploiDuTemps.objects.filter(empreinte=signature).first()
                if edt is None:
                    version = (EmploiDuTemps.objects.filter(
                        annee_academique=annee, population_type='GROUPE', population_id=groupe.pk,
                    ).aggregate(v=models.Max('version'))['v'] or 0) + 1
                    edt = EmploiDuTemps.objects.create(
                        annee_academique=annee, population_type='GROUPE', population_id=groupe.pk,
                        population_denominateur=f'{groupe.ref_formation.intitule} / {groupe.nom}',
                        titre=f'{MARQUE} EDT — {groupe.ref_formation.intitule} — {groupe.nom}'[:255],
                        statut='PUBLIE', semaine_debut=1, semaine_fin=semaine_fin,
                        rentree=annee.date_debut, cree_par=createur,
                        publie_par=createur, publie_le=now, version=version, empreinte=signature,
                        motif_modification=f'{MARQUE} Scénario pédagogique de démonstration.',
                    )
                    nb_edts += 1
                elif edt.semaine_fin != semaine_fin:
                    edt.semaine_fin = semaine_fin
                    edt.save(update_fields=['semaine_fin', 'updated_at'])
                edts.append(edt)
                equipe = list(candidates.filter(groupe=groupe).select_related(
                    'ecue', 'enseignant',
                ).order_by('ecue__code', 'pk')[:ECUE_PAR_GROUPE])
                for index, ap in enumerate(equipe):
                    debut, fin = HORAIRES[rang]
                    template, _ = CreneauTemplate.objects.get_or_create(
                        jour=JOURS[index], heure_debut=debut, heure_fin=fin,
                    )
                    salle = salles[rang]
                    seance, creee = AffectationCreneau.objects.update_or_create(
                        emploi_du_temps=edt, affectation_pedagogique=ap,
                        commentaire__startswith=MARQUE,
                        defaults={
                            'creneau_template': template, 'semaine_debut': 1,
                            'semaine_fin': semaine_fin, 'groupe': groupe,
                            'formation': ap.ref_formation, 'formateur': ap.enseignant,
                            'enseignant_nom': f'{ap.enseignant.nom} {ap.enseignant.prenom}',
                            'salle': salle, 'salle_nom': salle.nom, 'actif': True,
                            'nature': {'CM': 'COURS', 'TD': 'TD', 'TP': 'TP'}[ap.type_enseignement],
                            'intitule': f'{MARQUE} {ap.ecue.code} — {ap.ecue.intitule}'[:255],
                            'commentaire': f'{MARQUE} Seed EDT/présences v1 ; ECUE {ap.ecue.code}.',
                            'cree_par': createur,
                        },
                    )
                    nb_seances += int(creee)
            # Détection globale après création de tous les groupes : les conflits
            # inter-EDT (enseignant/salle) sont vérifiés, pas seulement en interne.
            for edt in edts:
                nb_conflits += detecter_conflits(edt)['conflits_detectes']

            seances = list(AffectationCreneau.objects.filter(
                emploi_du_temps__in=edts, actif=True,
            ).select_related('creneau_template', 'affectation_pedagogique__ecue',
                             'emploi_du_temps__annee_academique'))
            existants = set(Pointage.objects.filter(seance_edt__in=seances).values_list(
                'seance_edt_id', 'date_journee', 'participant_id',
            ))
            a_creer = []
            jour = annee.date_debut
            while jour <= dernier_jour:
                for seance in seances:
                    if not est_seance_du_jour(seance, jour):
                        continue
                    debut, fin = horodatages(seance, jour)
                    if fin >= now:
                        continue
                    ap = seance.affectation_pedagogique
                    for pid in sorted(membres[seance.groupe_id]):
                        if (seance.pk, jour, pid) in existants:
                            continue
                        a_creer.append(_pointage(ap, seance, pid, matricules, jour, debut, fin))
                        existants.add((seance.pk, jour, pid))
                jour += timedelta(days=1)
            Pointage.objects.bulk_create(a_creer, batch_size=500)
            nb_points = len(a_creer)
            if options['dry_run']:
                transaction.set_rollback(True)
        verbe = 'seraient créés' if options['dry_run'] else 'créés'
        self.stdout.write(self.style.SUCCESS(
            f'EDT d’exemple : {len(groupes)} groupes, {len(seances)} créneaux hebdomadaires '
            f'(S1–S{semaine_fin}), {nb_edts} EDT / {nb_seances} créneaux / {nb_points} pointages '
            f'{verbe} ; {nb_conflits} conflit(s) détecté(s). '
            f'Historique arrêté au {dernier_jour}, aucune présence future.'
        ))