"""Seed et validation idempotente du Lot 3.1 pour l'INJS Marcory.

Exécute de bout en bout :
1. Vérification des prérequis des Lots 1.1, 1.2 et 2.1
2. Complétude des modules opérationnels et rattachement des 6 ECUEs STAPS
3. Passerelle Inscriptions Pédagogiques LMD ↔ Modules Opérationnels
4. Modélisation des évaluations (CC et Examen Terminal), saisie des notes et verrouillage
5. Calcul des moyennes d'ECUE, d'UE et semestrielles avec compensation LMD
6. Délibération de la session de Jury LMD, génération du Procès-Verbal (PV) et décision ADMIS
7. Émission et validation des diplômes officiels scellés par empreinte SHA-256

Usage :
    python manage.py seed_lot3_1_evaluations_jurys
"""
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.db import transaction
from django.utils import timezone

from authentication.models import User
from formations.models import Formation, Module, NoteModuleColonne, NoteModule, RefFormation, RefModule, RefSite
from scolarite.models import (
    AnneeAcademique, Niveau, Parcours, Maquette, ECUE,
    InscriptionAdministrative, InscriptionPedagogique
)
from suiviEvaluation.models import MoyenneModule
from jurys.models import SessionJury, DecisionJury, PVJury
from jurys import services as jurys_services
from jurys.pv import generer_pv
from graduation.models import Diplome
from graduation.services import valider_diplome, verifier_par_token
from scolarite import passerelle_services


NOTES_ETUDIANTS_L3 = {
    'INJS26-0001': (Decimal('16.0'), Decimal('16.5'), 'Très Bien'), # KOUASSI
    'INJS26-0002': (Decimal('17.0'), Decimal('17.5'), 'Très Bien'), # TRAORE
    'INJS26-0003': (Decimal('14.5'), Decimal('15.0'), 'Bien'),      # KONE
    'INJS26-0004': (Decimal('15.5'), Decimal('16.0'), 'Bien'),      # DIABATE
    'INJS26-0005': (Decimal('15.0'), Decimal('15.5'), 'Bien'),      # N'GUESSAN
    'INJS26-0006': (Decimal('17.0'), Decimal('18.0'), 'Très Bien'), # OUATTARA
}


class Command(BaseCommand):
    help = "Initialise et valide le cycle d'évaluations, jurys LMD et diplômation SHA-256 (Lot 3.1)."

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write("--- 1. Vérification des prérequis LMD (Lots 1.1, 1.2, 2.1) ---")
        call_command('seed_lot2_1_edts')

        admin_user = User.objects.filter(is_superuser=True).first() or User.objects.first()
        annee = AnneeAcademique.objects.get(libelle='2026-2027')
        ref_form = RefFormation.objects.first()
        l3 = Niveau.objects.get(code='L3')
        if l3.credits_requis != 30:
            l3.credits_requis = 30
            l3.save(update_fields=['credits_requis'])

        parcours = Parcours.objects.get(code='PROF_COLLEGE')
        maquette = Maquette.objects.get(ref_formation=ref_form, niveau=l3, statut=Maquette.Statut.ACTIVE)
        form_op = Formation.objects.filter(ref_formation=ref_form).first()
        if not form_op:
            form_op, _ = Formation.objects.get_or_create(
                ref_formation=ref_form,
                defaults={'formation': ref_form.intitule}
            )
        site = RefSite.objects.get(nom='Campus INJS Marcory (Abidjan)')

        self.stdout.write("--- 2. Modules opérationnels & Rattachement RefModules ---")
        ref_athle, _ = RefModule.objects.get_or_create(intitule='ATHLÉTISME ET PRATIQUES SPORTIVES')
        ref_dida, _ = RefModule.objects.get_or_create(intitule='DIDACTIQUE ET PÉDAGOGIE STAPS')
        ref_biomeca, _ = RefModule.objects.get_or_create(intitule='BIOMÉCANIQUE ET PHYSIOLOGIE DE L\'EFFORT')
        ref_sante, _ = RefModule.objects.get_or_create(intitule='SANTÉ, HYGIÈNE ET SECOURISME')
        ref_deonto = RefModule.objects.filter(intitule__icontains='DÉONTOLOGIE').first()
        ref_manage = RefModule.objects.filter(intitule__icontains='LEADERSHIP').first()

        modules_specs = [
            (ref_athle, 'Athlétisme et pratiques sportives', 70, 'Gymnase Omnisports Central'),
            (ref_dida, 'Didactique et pédagogie STAPS', 60, 'Salle STAPS 101'),
            (ref_biomeca, 'Biomécanique et physiologie de l\'effort', 60, 'Amphithéâtre A'),
            (ref_sante, 'Santé, hygiène et secourisme', 50, 'Salle STAPS 102'),
            (ref_deonto, 'Déontologie et Fonction Publique', 35, 'Salle STAPS 101'),
            (ref_manage, 'Leadership, Management et Droit Administratif', 35, 'Amphithéâtre A'),
        ]

        modules_crees = []
        for ref_m, intitule, volume, salle in modules_specs:
            mod = Module.objects.filter(formation=form_op, intitule=intitule).first()
            if not mod:
                mod = Module.objects.create(
                    formation=form_op, intitule=intitule, ref_module=ref_m,
                    duree_prevue_heures=volume, site=site, salle=salle
                )
            else:
                if mod.ref_module_id != ref_m.id or mod.site_id != site.id:
                    mod.ref_module = ref_m
                    mod.site = site
                    mod.salle = salle
                    mod.save(update_fields=['ref_module', 'site', 'salle'])
            modules_crees.append(mod)

        # Mettre à jour les ECUEs de la maquette
        ECUE.objects.filter(code='ECUE511').update(ref_module=ref_athle)
        ECUE.objects.filter(code='ECUE512').update(ref_module=ref_dida)
        ECUE.objects.filter(code='ECUE521').update(ref_module=ref_biomeca)
        ECUE.objects.filter(code='ECUE522').update(ref_module=ref_sante)
        ECUE.objects.filter(code='ECUE531').update(ref_module=ref_deonto)
        ECUE.objects.filter(code='ECUE532').update(ref_module=ref_manage)

        self.stdout.write("--- 3. Synchronisation Passerelle Pédagogique ---")
        inscriptions = list(InscriptionAdministrative.objects.filter(
            annee_academique=annee, ref_formation=ref_form, statut=InscriptionAdministrative.Statut.VALIDEE
        ))
        res_passerelle = passerelle_services.synchroniser_lot(inscriptions, form_op, acteur=admin_user)

        # Assurer la liaison explicite IP -> ModuleParticipant
        for ia in inscriptions:
            for ip in ia.inscriptions_pedagogiques.select_related('ecue__ref_module'):
                if not ip.module_participant_id and ip.ecue.ref_module_id:
                    mp = form_op.modules.filter(ref_module=ip.ecue.ref_module).first()
                    if mp:
                        from formations.models import ModuleParticipant
                        mp_obj = ModuleParticipant.objects.filter(module=mp, participant=ia.etudiant.participant).first()
                        if mp_obj:
                            ip.module_participant = mp_obj
                            ip.statut = InscriptionPedagogique.Statut.VALIDEE
                            ip.save(update_fields=['module_participant', 'statut'])
                elif ip.module_participant_id:
                    ip.statut = InscriptionPedagogique.Statut.VALIDEE
                    ip.save(update_fields=['statut'])

        self.stdout.write(f"  Passerelle synchronisée pour {len(inscriptions)} étudiants ({res_passerelle['creees']} liaisons)")

        self.stdout.write("--- 4. Saisie des Évaluations (CC & Examen Terminal) ---")
        for m in modules_crees:
            col_cc, _ = NoteModuleColonne.objects.get_or_create(
                module=m, libelle='Contrôle Continu', defaults={'note_max': Decimal('20'), 'ordre': 1}
            )
            col_et, _ = NoteModuleColonne.objects.get_or_create(
                module=m, libelle='Examen Terminal', defaults={'note_max': Decimal('20'), 'ordre': 2}
            )
            for ia in inscriptions:
                part = ia.etudiant.participant
                ncc, net, _ = NOTES_ETUDIANTS_L3[part.matricule]
                offset = Decimal((m.id % 3) * 0.25)
                v_cc = min(Decimal('20.0'), ncc + offset)
                v_et = min(Decimal('20.0'), net + offset)

                NoteModule.objects.update_or_create(
                    colonne=col_cc, participant=part,
                    defaults={
                        'note': v_cc, 'statut_validation': NoteModule.StatutValidation.VALIDEE,
                        'verrouillee': True, 'saisie_par': admin_user, 'validation_par': admin_user,
                        'validation_le': timezone.now()
                    }
                )
                NoteModule.objects.update_or_create(
                    colonne=col_et, participant=part,
                    defaults={
                        'note': v_et, 'statut_validation': NoteModule.StatutValidation.VALIDEE,
                        'verrouillee': True, 'saisie_par': admin_user, 'validation_par': admin_user,
                        'validation_le': timezone.now()
                    }
                )
                MoyenneModule.objects.update_or_create(
                    module=m, participant=part,
                    defaults={
                        'moyenne': (v_cc + v_et) / 2, 'nb_notes': 2, 'heures_presence': Decimal('30'),
                        'heures_prevues': Decimal('30'), 'taux_presence': Decimal('100'),
                        'calculee_le': timezone.now()
                    }
                )

        self.stdout.write(f"  Évaluations validées et verrouillées pour {len(modules_crees)} modules")

        self.stdout.write("--- 5. Délibération de la Session de Jury LMD ---")
        session = SessionJury.objects.filter(
            annee_academique=annee, ref_formation=ref_form, parcours=parcours, niveau=l3,
            type_session=SessionJury.TypeSession.NORMALE
        ).first()

        if not session:
            session = SessionJury.objects.create(
                annee_academique=annee, ref_formation=ref_form, parcours=parcours, niveau=l3,
                maquette=maquette, type_session=SessionJury.TypeSession.NORMALE,
                libelle='Session de Jury LMD L3 STAPS 2026-2027', creee_par=admin_user,
            )

        # Workflow conditionnel selon l'état actuel de la session
        if session.statut == SessionJury.Statut.PREPARATION:
            session = jurys_services.transition(session, admin_user) # -> CONTROLE
        if session.statut == SessionJury.Statut.CONTROLE:
            session = jurys_services.transition(session, admin_user) # -> CALCUL

        if session.statut == SessionJury.Statut.CALCUL:
            jurys_services.calculer_propositions(session, admin_user)
            session = jurys_services.transition(session, admin_user) # -> DELIBERATION

        if session.statut == SessionJury.Statut.DELIBERATION:
            for ia in inscriptions:
                part = ia.etudiant.participant
                _, _, mention = NOTES_ETUDIANTS_L3[part.matricule]
                jurys_services.enregistrer_decision(
                    session, ia, 'ADMIS', admin_user,
                    mention=mention, justification='Validation semestrielle collégiale 30 ECTS'
                )
            session = jurys_services.transition(session, admin_user) # -> DECISION

        if not PVJury.objects.filter(session=session).exists():
            if session.statut != SessionJury.Statut.DECISION:
                session.statut = SessionJury.Statut.DECISION
                session.save(update_fields=['statut'])
            pv = generer_pv(session, admin_user)
            self.stdout.write(f"  PV de Jury généré : {pv.fichier.name} (SHA-256 : {pv.sha256[:16]}...)")

        if session.statut == SessionJury.Statut.DECISION:
            session = jurys_services.transition(session, admin_user) # -> PV_GENERE

        if session.statut == SessionJury.Statut.PV_GENERE:
            session = jurys_services.transition(session, admin_user) # -> VALIDE

        if session.statut == SessionJury.Statut.VALIDE:
            session = jurys_services.transition(session, admin_user) # -> VERROUILLE

        if session.statut == SessionJury.Statut.VERROUILLE:
            session = jurys_services.publier(session, admin_user) # -> PUBLIE

        self.stdout.write(f"  Session de Jury délibérée et clôturée : {session.libelle} (Statut : {session.statut})")

        self.stdout.write("--- 6. Émission et Scellement des Diplômes SHA-256 ---")
        diplomes_valides = 0
        for ia in inscriptions:
            part = ia.etudiant.participant
            dec = DecisionJury.objects.get(session=session, inscription=ia)
            diplome, _ = Diplome.objects.get_or_create(
                etudiant=ia.etudiant,
                annee_academique=annee,
                ref_formation=ref_form,
                parcours=parcours,
                niveau=l3,
                defaults={
                    'session_jury': session,
                    'decision_jury': dec,
                    'credits_acquis': dec.credits_acquis,
                    'mention': dec.mention,
                }
            )
            if diplome.statut != Diplome.Statut.VALIDATED:
                valider_diplome(diplome, admin_user)

            verif = verifier_par_token(diplome.numero_unique)
            if verif.get('valide'):
                diplomes_valides += 1
                self.stdout.write(
                    f"  Diplôme officiel : {diplome.numero_unique} | Étudiant : {part.matricule} ({part.nom} {part.prenom}) | "
                    f"Mention : {diplome.mention} | SHA-256 : {diplome.empreinte_pdf[:16]}... | Certifié : {verif['valide']}"
                )

        self.stdout.write(self.style.SUCCESS(
            f"=== Lot 3.1 initialisé et validé avec succès ({diplomes_valides} diplômes certifiés SHA-256) ==="
        ))
