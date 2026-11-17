"""Compléter EN LOCAL le jeu de démonstration 3500 → 5000 d'une capture.

Ne copie aucune donnée du site public. Préserve les 3500 profils existants et
leurs relations ; crée seulement des profils fictifs identifiables. Le fichier
SQLite cible doit être sauvegardé et vérifié par l'opérateur avant --appliquer.
Jamais de commande de production : profil Arena + SQLite dans le dépôt requis.
"""
from collections import defaultdict
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.db.models import Count
from django.utils import timezone

from admissions.management.commands.seed_candidatures_demo import Command as AdmissionsSeed
from authentication.models import User
from formations.models import Formateur, Participant
from scolarite.models import (
    AffectationGroupe, AnneeAcademique, Groupe, InscriptionAdministrative,
)


COHORTE_INITIALE = 3500
COHORTE_CIBLE = 5000
ENSEIGNANTS_INITIAUX = 67
ENSEIGNANTS_CIBLES = 93
GROUPES_SANS_CHARGE_INITIAUX = 130
GROUPES_SANS_CHARGE_CIBLES = 177
MARQUE = '[Exemple] Complément de la capture dashboard (données fictives).'


class Command(BaseCommand):
    help = 'Complète la démo Arena de 3500 à 5000 étudiants sans purger les données existantes.'

    def add_arguments(self, parser):
        parser.add_argument('--base', required=True, help='Chemin absolu exact du SQLite ciblé.')
        parser.add_argument('--appliquer', action='store_true')
        parser.add_argument('--confirmer', default='')

    def _cohorte(self):
        return Participant.objects.filter(email__regex=r'\.\d+@exemple\.ci$')

    def handle(self, *args, **options):
        root = Path(settings.BASE_DIR).parent.resolve()
        cible = Path(settings.DATABASES['default']['NAME']).resolve()
        if (settings.SETTINGS_MODULE != 'arena.settings_sandbox'
                or not settings.DEBUG or connection.vendor != 'sqlite'
                or not cible.is_relative_to(root)
                or str(cible) != options['base']):
            raise CommandError('Réservé à la base SQLite locale de l’aperçu Arena, chemin exact requis.')
        annee = AnneeAcademique.objects.filter(courante=True, actif=True).first()
        if annee is None:
            raise CommandError('Année académique courante absente.')
        inscrits = InscriptionAdministrative.objects.filter(
            annee_academique=annee,
            statut=InscriptionAdministrative.Statut.VALIDEE,
            etudiant__participant__in=self._cohorte(),
        ).count()
        existants = self._cohorte().count()
        enseignants = Formateur.objects.count()
        groupes_sans_charge = Groupe.objects.filter(
            actif=True, affectations_pedagogiques__isnull=True,
        ).count()
        self.stdout.write(
            f'Année {annee.libelle} ; cohorte fictive {existants}, '
            f'inscriptions validées {inscrits}, enseignants {enseignants}.')
        if (existants == COHORTE_CIBLE and inscrits == COHORTE_CIBLE
                and enseignants == ENSEIGNANTS_CIBLES
                and groupes_sans_charge == GROUPES_SANS_CHARGE_CIBLES):
            self.stdout.write('Déjà complété : aucune écriture.')
            return
        if (existants, inscrits, enseignants, groupes_sans_charge) != (
                COHORTE_INITIALE, COHORTE_INITIALE, ENSEIGNANTS_INITIAUX,
                GROUPES_SANS_CHARGE_INITIAUX):
            raise CommandError('État inattendu : aucun ajout, ne pas mélanger les cohortes.')
        # Le suffixe 3501..5000 est réservé au complément et ne doit jamais
        # pointer vers un profil ou candidat préexistant.
        if self._cohorte().filter(email__regex=r'\.(350[1-9]|35[1-9][0-9]|3[6-9][0-9]{2}|4[0-9]{3}|5000)@exemple\.ci$').exists():
            raise CommandError('Suffixe du complément déjà utilisé : opération refusée.')
        if not options['appliquer']:
            self.stdout.write('Simulation seule : +1500 étudiants fictifs, +26 enseignants fictifs. '
                              'Sauvegarder et vérifier le SQLite avant --appliquer --confirmer DEMO_FICTIVE.')
            return
        if options['confirmer'] != 'DEMO_FICTIVE':
            raise CommandError('Confirmation DEMO_FICTIVE requise après sauvegarde vérifiée.')

        with transaction.atomic():
            avant = set(self._cohorte().values_list('pk', flat=True))
            seed = AdmissionsSeed(stdout=self.stdout)
            seed.effectif_cible = COHORTE_CIBLE - COHORTE_INITIALE
            seed.aujourdhui = timezone.localdate()
            seed.acteur = User.objects.filter(username='admin').first()
            seed._effectifs_etudiants(annee, {'etudiants': 0}, indice_initial=COHORTE_INITIALE)
            nouveaux = self._cohorte().exclude(pk__in=avant)
            if nouveaux.count() != COHORTE_CIBLE - COHORTE_INITIALE:
                raise CommandError('Effectif créé incohérent : transaction annulée.')
            self._groupes(annee, nouveaux)
            for numero in range(1, ENSEIGNANTS_CIBLES - ENSEIGNANTS_INITIAUX + 1):
                Formateur.objects.create(
                    numerobadge=f'ENS-CAPTURE-{numero:03d}',
                    nom='ENSEIGNANT DÉMO', prenom=f'Profil {numero:02d}',
                    email=f'capture.enseignant{numero:02d}@exemple.injs.ci',
                    organisation='INJS (démonstration)',
                    specialite='Accompagnement pédagogique (démonstration)',
                    observations=MARQUE,
                )
            if (self._cohorte().count() != COHORTE_CIBLE
                    or Formateur.objects.count() != ENSEIGNANTS_CIBLES):
                raise CommandError('Compteurs finaux incohérents : transaction annulée.')
        self.stdout.write(self.style.SUCCESS('Complément local terminé ; dossiers préexistants préservés.'))

    def _groupes(self, annee, nouveaux):
        """Remplir les places libres, puis ouvrir des sections sans surcapacité."""
        inscriptions = list(InscriptionAdministrative.objects.filter(
            annee_academique=annee, etudiant__participant__in=nouveaux,
            statut=InscriptionAdministrative.Statut.VALIDEE,
        ).order_by('id'))
        cohortes = defaultdict(list)
        for insc in inscriptions:
            cohortes[(insc.ref_formation_id, insc.niveau_id)].append(insc)
        occupation = dict(AffectationGroupe.objects.filter(
            active=True, groupe__annee_academique=annee,
        ).values('groupe_id').annotate(n=Count('id')).values_list('groupe_id', 'n'))
        affectations = []
        nouveaux_groupes = []
        for (formation_id, niveau_id), membres in sorted(cohortes.items()):
            tous_groupes = list(Groupe.objects.filter(
                annee_academique=annee, ref_formation_id=formation_id,
                niveau_id=niveau_id,
            ).order_by('id'))
            groupes = [g for g in tous_groupes if g.actif]
            if not groupes:
                raise CommandError('Cohorte sans groupe initial : transaction annulée.')
            plafond = next((g.capacite_max for g in groupes if g.capacite_max), 35)
            numero = 1
            for groupe in tous_groupes:
                if groupe.nom.startswith(f'{membres[0].niveau.code}-G'):
                    fin = groupe.nom.rsplit('G', 1)[-1]
                    if fin.isdigit():
                        numero = max(numero, int(fin) + 1)
            places = [(g, max(0, g.capacite_max - occupation.get(g.pk, 0))
                       if g.capacite_max is not None else None) for g in groupes]
            index = 0
            for insc in membres:
                while index < len(places) and places[index][1] == 0:
                    index += 1
                if index == len(places):
                    nom = f'{insc.niveau.code}-G{numero}'
                    numero += 1
                    groupe = Groupe.objects.create(
                        annee_academique=annee, ref_formation_id=formation_id,
                        niveau_id=niveau_id, nom=nom, capacite_max=plafond,
                    )
                    places.append((groupe, plafond))
                    nouveaux_groupes.append(groupe)
                groupe, libres = places[index]
                places[index] = (groupe, libres - 1 if libres is not None else None)
                affectations.append(AffectationGroupe(
                    inscription=insc, groupe=groupe,
                    date_debut=timezone.localdate() - timedelta(days=20),
                    motif=MARQUE,
                ))
        # La capture montre 177 sections sans CHARGE pédagogique. Répartir
        # aussi les nouveaux inscrits entre des sections supplémentaires,
        # plutôt que créer 14 groupes artificiellement vides ou déplacer les
        # affectations historiques. Toutes les sections ont des étudiants.
        a_ouvrir = GROUPES_SANS_CHARGE_CIBLES - Groupe.objects.filter(
            actif=True, affectations_pedagogiques__isnull=True,
        ).count()
        par_groupe = defaultdict(list)
        nouveaux_ids = {g.pk for g in nouveaux_groupes}
        for aff in affectations:
            if aff.groupe_id in nouveaux_ids:
                par_groupe[aff.groupe_id].append(aff)
        sources = sorted(
            (g for g in nouveaux_groupes if len(par_groupe[g.pk]) >= 4),
            key=lambda g: (-len(par_groupe[g.pk]), g.pk),
        )
        if a_ouvrir < 0 or len(sources) < a_ouvrir:
            raise CommandError('Sections complémentaires insuffisantes : transaction annulée.')
        for source in sources[:a_ouvrir]:
            tous_noms = Groupe.objects.filter(
                annee_academique=annee, ref_formation_id=source.ref_formation_id,
                niveau_id=source.niveau_id,
            ).values_list('nom', flat=True)
            prefixe = f'{source.niveau.code}-G'
            numero = 1 + max((int(nom[len(prefixe):]) for nom in tous_noms
                              if nom.startswith(prefixe) and nom[len(prefixe):].isdigit()),
                             default=0)
            section = Groupe.objects.create(
                annee_academique=annee, ref_formation_id=source.ref_formation_id,
                niveau_id=source.niveau_id, nom=f'{prefixe}{numero}',
                capacite_max=source.capacite_max,
            )
            etudiants = par_groupe[source.pk]
            for aff in etudiants[len(etudiants) // 2:]:
                aff.groupe = section
        AffectationGroupe.objects.bulk_create(affectations, batch_size=500)
        if len(affectations) != COHORTE_CIBLE - COHORTE_INITIALE:
            raise CommandError('Affectations incomplètes : transaction annulée.')
