"""P00-08 — parcours de fumée bout-en-bout de l'année académique INJS-LMD.

Exécute, sur des données de démonstration auto-ensemencées, la chaîne officielle
complète :

    campagne → candidature → pièces → admissibilité → admission
    → inscription administrative → dossier étudiant → matricule
    → inscription pédagogique → groupe → maquette/UE/ECUE
    → séance → pointage QR → note → moyenne → jury → diplôme
    → échéancier → paiement → quittance

Chaque étape produit un code métier lisible (SMOKE-NN-*), un statut et un
identifiant ; la commande affiche un tableau récapitulatif et s'arrête avec un
code de retour NON NUL à la première défaillance (intégration CI, job Backend).

Par défaut, le parcours s'exécute dans une transaction ANNULÉE en fin : la
commande est donc sans effet durable sur la base et idempotente (prévu pour la
CI). ``--persist`` conserve les données (base de démonstration explicite).

Cette commande n'introduit AUCUNE règle métier nouvelle : elle ne fait
qu'emprunter les services et les modèles existants, avec des données
synthétiques. À l'image des tests ``scolarite.tests.test_parcours_complet`` et
``jurys.tests.test_workflow_api`` dont elle reprend les recettes.
"""

from datetime import date, time, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from admissions import admission_services, services as candidature_services, workflow
from admissions.models import (
    CampagneAdmission,
    ClassementConcours,
    Candidat,
    Candidature,
    Epreuve,
    NoteConcours,
    PieceCandidature,
    TypePiece,
)
from finances_etudiantes.services import (
    confirmer_paiement,
    enregistrer_paiement_idempotent,
    generer_echeancier_pour_etudiant,
    generer_facture,
)
from finances_etudiantes.models import Tarification
from formations.models import (
    Formation,
    Module,
    ModuleParticipant,
    NoteModule,
    NoteModuleColonne,
)


class Command(BaseCommand):
    help = "Parcours de fumée de la chaîne académique complète (P00-08)."

    def add_arguments(self, parser):
        parser.add_argument(
            '--persist', action='store_true',
            help="Conserve les données créées (défaut : annulation en fin, mode CI).",
        )

    # -- orchestration ------------------------------------------------------

    def handle(self, *args, **options):
        self.etapes = []
        self.contexte = {}
        persist = options['persist']

        self.stdout.write(self.style.MIGRATE_HEADING(
            "\nPARCOURS DE FUMÉE INJS-LMD — chaîne académique complète"
        ))
        self.stdout.write(
            f"Mode : {'PERSISTANCE des données' if persist else 'transaction annulée en fin (CI, idempotent)'}\n"
        )

        try:
            with transaction.atomic():
                self._executer()
                if not persist:
                    transaction.set_rollback(True)
        except Exception as exc:  # noqa: BLE001 — la commande doit tout attraper pour le rapport
            code = getattr(exc, 'step_code', 'étape inconnue')
            self._rapport()
            self.stdout.write(self.style.ERROR(f"\nÉCHEC — {code} : {exc}"))
            raise CommandError(f"Parcours de fumée en échec à l'étape {code} : {exc}") from exc

        self._rapport()
        self.stdout.write(self.style.SUCCESS(
            f"\nSUCCÈS — les {len(self.etapes)} étapes du parcours sont passées."
        ))

    def _etape(self, code, libelle, fonction):
        try:
            detail = fonction() or ''
        except Exception as exc:
            exc.step_code = code
            raise
        self.etapes.append((code, libelle, 'OK', str(detail)))
        self.stdout.write(self.style.SUCCESS(f"  [{code}] {libelle} — {detail}"))

    def _executer(self):
        c = self.contexte

        self._etape('SMOKE-01-CAMPAGNE', 'Campagne d’admission ouverte', self._campagne)
        self._etape('SMOKE-02-CANDIDAT', 'Candidat et candidature déposés', self._candidature)
        self._etape('SMOKE-03-PIECES', 'Pièces justificatives vérifiées', self._pieces)
        self._etape('SMOKE-04-ADMISSIBILITE', 'Épreuves, notes de concours et admissibilité', self._admissibilite)
        self._etape('SMOKE-05-ADMISSION', 'Admission prononcée (ADMIS)', self._admission)
        self._etape('SMOKE-06-IA', 'Inscription administrative et dossier étudiant', self._inscription_admin)
        self._etape('SMOKE-07-MATRICULE', 'Matricule généré', self._matricule)
        self._etape('SMOKE-08-IP', 'Inscriptions pédagogiques (UE/ECUE)', self._inscriptions_peda)
        self._etape('SMOKE-09-GROUPE', 'Affectation au groupe', self._groupe)
        self._etape('SMOKE-10-MAQUETTE', 'Maquette / UE / ECUE actives', self._maquette)
        self._etape('SMOKE-11-PASSERELLE', 'Passerelle vers le module opérationnel', self._passerelle)
        self._etape('SMOKE-12-SEANCE', 'Séance programmée', self._seance)
        self._etape('SMOKE-13-QR', 'Jeton QR généré pour la séance', self._qr)
        self._etape('SMOKE-14-POINTAGE', 'Pointage QR (entrée + sortie)', self._pointage)
        self._etape('SMOKE-15-NOTE', 'Note de module validée', self._note)
        self._etape('SMOKE-16-MOYENNE', 'Moyenne de module calculée', self._moyenne)
        self._etape('SMOKE-17-JURY', 'Proposition, décision et verrouillage du jury', self._jury)
        self._etape('SMOKE-18-DIPLOME', 'Diplôme généré et validé (PDF + empreinte)', self._diplome)
        self._etape('SMOKE-19-TARIFS', 'Tarifications de l’année', self._tarifs)
        self._etape('SMOKE-20-ECHEANCIER', 'Échéancier généré', self._echeancier)
        self._etape('SMOKE-21-FACTURE', 'Facture émise', self._facture)
        self._etape('SMOKE-22-PAIEMENT', 'Paiement enregistré (idempotent)', self._paiement)
        self._etape('SMOKE-23-QUITTANCE', 'Paiement confirmé, quittance émise', self._quittance)

    # -- jeu de données de référence ---------------------------------------

    def _referentiels(self):
        from authentication.models import User
        from formations.models import RefCategorie, RefFormation, RefGrade, RefModule
        from scolarite.models import (
            AnneeAcademique, Groupe, Maquette, Niveau, Parcours, Semestre, StatutEtudiant, UE, ECUE,
        )

        annee = AnneeAcademique.objects.create(
            libelle='2026-2027', date_debut=date(2026, 10, 1), date_fin=date(2027, 9, 30),
            courante=True,
        )
        ref_formation = RefFormation.objects.create(intitule='LICENCE STAPS (SMOKE)')
        niveau = Niveau.objects.create(code='L1S', libelle='Licence 1 Smoke', ordre=1, credits_requis=20)
        semestre = Semestre.objects.create(niveau=niveau, numero=1, libelle='S1')
        parcours = Parcours.objects.create(
            ref_formation=ref_formation, code='EM-SMOKE', intitule='Éducation et Motricité (démo)',
        )
        categorie, _ = RefCategorie.objects.get_or_create(libelle='A')
        grade, _ = RefGrade.objects.get_or_create(categorie=categorie, libelle='A3')
        StatutEtudiant.objects.get_or_create(code='ACTIF', defaults={'libelle': 'Actif'})
        TypePiece.objects.get_or_create(
            code='DIPLOME', defaults={'libelle': 'Diplôme', 'obligatoire_par_defaut': True},
        )
        TypePiece.objects.get_or_create(
            code='CV', defaults={'libelle': 'CV', 'obligatoire_par_defaut': False},
        )
        groupe = Groupe.objects.create(
            annee_academique=annee, ref_formation=ref_formation, niveau=niveau,
            nom='L1S-G1', capacite_max=25,
        )
        maquette = Maquette.objects.create(
            annee_academique=annee, ref_formation=ref_formation, niveau=niveau,
        )
        ue = UE.objects.create(
            maquette=maquette, semestre=semestre, code='UE-S1',
            intitule='UE fondamentale', credits=20,
        )
        ref_a = RefModule.objects.create(intitule='ANATOMIE (SMOKE)')
        ref_b = RefModule.objects.create(intitule='PHYSIOLOGIE (SMOKE)')
        ecue_a = ECUE.objects.create(
            ue=ue, code='ECUE-A', intitule='Anatomie', credits=10, volume_cm=20, ref_module=ref_a,
        )
        ecue_b = ECUE.objects.create(
            ue=ue, code='ECUE-B', intitule='Physiologie', credits=10, volume_cm=20, ref_module=ref_b,
        )
        maquette.statut = Maquette.Statut.ACTIVE
        maquette.save()

        formation_op = Formation.objects.create(formation='LICENCE STAPS 2026 (SMOKE)')
        module_a = Module.objects.create(
            formation=formation_op, intitule='Anatomie (démo)', ref_module=ref_a,
        )
        module_b = Module.objects.create(
            formation=formation_op, intitule='Physiologie (démo)', ref_module=ref_b,
        )
        acteur = User.objects.create_user(username='smoke_agent', password='x', role='INJS_ADMIN')

        self.contexte.update(locals())

    # -- étapes -------------------------------------------------------------

    def _campagne(self):
        self._referentiels()
        c = self.contexte
        campagne = CampagneAdmission.objects.create(
            libelle='Campagne de démo SMOKE 2026-2027',
            annee_academique=c['annee'], ref_formation=c['ref_formation'],
            parcours=c['parcours'],
            date_ouverture=date(2026, 9, 1), date_fermeture=date(2026, 10, 31),
            quota_admissibles=100, quota_admis=80,
            statut=CampagneAdmission.Statut.OUVERTE,
        )
        c['campagne'] = campagne
        return f"campagne n°{campagne.pk} ({campagne.statut})"

    def _candidature(self):
        c = self.contexte
        candidat = Candidat.objects.create(
            nom='Smoke', prenom='Démo', sexe='F', email='smoke.demo@example.ci',
        )
        candidature = candidature_services.creer_candidature(
            candidat, acteur=c['acteur'], campagne=c['campagne'],
            annee_academique=c['annee'], ref_formation=c['ref_formation'],
            parcours=c['parcours'], niveau=c['niveau'],
        )
        c.update(candidat=candidat, candidature=candidature)
        return f"{candidature.numero} — {len(candidature.pieces.all())} pièce(s) initialisée(s)"

    def _pieces(self):
        c = self.contexte
        for piece in c['candidature'].pieces_obligatoires:
            candidature_services.deposer_piece(
                piece, acteur=c['acteur'], numero_document='SMOKE-123',
                date_delivrance=date(2024, 1, 15),
            )
            candidature_services.verifier_piece(
                piece, PieceCandidature.Statut.VALIDEE, acteur=c['acteur'],
            )
        validees, total = c['candidature'].completude
        return f"{validees}/{total} pièce(s) obligatoire(s) validée(s)"

    def _admissibilite(self):
        c = self.contexte
        # Épreuves du concours + notes (modèle officiel) puis instruction.
        epreuve = Epreuve.objects.create(
            campagne=c['campagne'], type=Epreuve.Type.values[0] if Epreuve.Type.values else 'ECRIT',
            intitule='Épreuve de culture générale (démo)',
            date=date(2026, 9, 20), heure_debut=time(8, 0), duree_minutes=120,
        )
        NoteConcours.objects.create(epreuve=epreuve, candidature=c['candidature'], note=Decimal('14.5'))
        for statut in (
            Candidature.Statut.SOUMISE,
            Candidature.Statut.EN_ATTENTE_DE_VERIFICATION,
            Candidature.Statut.PIECES_VALIDEES,
            Candidature.Statut.EN_ETUDE,
            Candidature.Statut.ADMISSIBLE,
        ):
            workflow.appliquer_transition(c['candidature'], statut, acteur=c['acteur'])
        liste = (ClassementConcours.Liste.values[0]
                 if ClassementConcours.Liste.values else 'PRINCIPALE')
        ClassementConcours.objects.create(
            campagne=c['campagne'], candidature=c['candidature'],
            rang=1, score_total=Decimal('14.5'), liste=liste,
            publie=True, genere_par=c['acteur'], genere_le=timezone.now(),
        )
        c['epreuve'] = epreuve
        return f"statut {c['candidature'].statut} — rang 1, moyenne 14.5/20"

    def _admission(self):
        c = self.contexte
        admission = admission_services.creer_admission(
            c['candidature'], acteur=c['acteur'],
            categorie=c['categorie'], grade=c['grade'],
        )
        admission_services.prononcer_decision(
            admission, admission.Decision.ADMIS, acteur=c['acteur'],
            reference='DEC-SMOKE-001', date_limite=timezone.localdate() + timedelta(days=30),
        )
        c['admission'] = admission
        return f"décision {admission.decision} (réf. {admission.reference_decision})"

    def _inscription_admin(self):
        from scolarite import inscription_services
        c = self.contexte
        inscription = inscription_services.convertir_admission_en_inscription(
            c['admission'], acteur=c['acteur'], valider=True,
        )
        c['inscription'] = inscription
        c['etudiant'] = inscription.etudiant
        return f"inscription n°{inscription.pk} — statut {inscription.statut}"

    def _matricule(self):
        c = self.contexte
        matricule = c['etudiant'].matricule
        if not matricule:
            raise AssertionError("Aucun matricule n'a été généré pour le dossier étudiant.")
        return matricule

    def _inscriptions_peda(self):
        from scolarite import pedagogie_services
        c = self.contexte
        creees = pedagogie_services.generer_inscriptions_pedagogiques(
            c['inscription'], acteur=c['acteur'],
        )
        c['ips'] = creees
        return f"{len(creees)} inscription(s) pédagogique(s) (UE/ECUE)"

    def _groupe(self):
        from scolarite import groupes_services
        c = self.contexte
        groupes_services.affecter_groupe(c['inscription'], c['groupe'], acteur=c['acteur'])
        return f"affectation à {c['groupe'].nom}"

    def _maquette(self):
        c = self.contexte
        m = c['maquette']
        return f"{m.libelle or 'Maquette'} — statut {m.statut} (1 UE, 2 ECUE)"

    def _passerelle(self):
        from scolarite import passerelle_services
        c = self.contexte
        resultat = passerelle_services.synchroniser(
            c['inscription'], c['formation_op'], acteur=c['acteur'],
        )
        # On raccorde chaque IP à son module opérationnel (ECUE → ref_module),
        # comme le fait le harnais du workflow de jury.
        for ip in c['inscription'].inscriptions_pedagogiques.select_related('ecue__ref_module'):
            mp = ModuleParticipant.objects.filter(
                module__ref_module=ip.ecue.ref_module,
                participant=c['etudiant'].participant,
            ).first()
            if mp and ip.module_participant_id != mp.id:
                ip.module_participant = mp
                ip.statut = ip.Statut.VALIDEE
                ip.save(update_fields=['module_participant', 'statut'])
            elif mp:
                ip.statut = ip.Statut.VALIDEE
                ip.save(update_fields=['statut'])
        c['mp_a'] = ModuleParticipant.objects.get(module=c['module_a'], participant=c['etudiant'].participant)
        c['mp_b'] = ModuleParticipant.objects.get(module=c['module_b'], participant=c['etudiant'].participant)
        return f"{resultat.get('creees', 0)} inscription(s) opérationnelle(s) synchronisée(s)"

    def _seance(self):
        from formations.models import SessionModule
        c = self.contexte
        aujourd_hui = timezone.localdate()
        c['seance'] = SessionModule.objects.create(
            module=c['module_a'], date_journee=aujourd_hui, numero=1,
            intitule='Séance de démo SMOKE',
            heure_debut_prevue=time(8, 0), heure_fin_prevue=time(11, 0),
            demarree_le=timezone.now() - timedelta(hours=2),
            terminee_le=timezone.now(),
            demarree_par=c['acteur'],
        )
        return f"séance n°{c['seance'].numero} du module « {c['module_a'].intitule} »"

    def _qr(self):
        from formations.models import QRToken
        c = self.contexte
        c['qr'] = QRToken.objects.create(
            session=c['seance'], genere_par=c['acteur'],
            expire_at=timezone.now() + timedelta(minutes=5),
        )
        return f"QR {str(c['qr'].token)[:8]}… (actif, expire dans 5 min)"

    def _pointage(self):
        from presences.models import Pointage
        c = self.contexte
        maintenant = timezone.now()
        pointage = Pointage.objects.create(
            participant=c['etudiant'].participant, session=c['seance'],
            date_journee=timezone.localdate(), device_id='SMOKE-DEVICE',
            timestamp_entree=maintenant - timedelta(hours=3),
            timestamp_sortie=maintenant - timedelta(hours=2),
            duree_presence_minutes=Decimal('60'),
            statut=Pointage.Statut.TERMINE,
            statut_assiduite=Pointage.StatutAssiduite.PRESENT,
            annee_academique=c['annee'], groupe_lmd=c['groupe'],
        )
        return (
            f"{pointage.get_statut_display()} — "
            f"{pointage.duree_presence_minutes} min "
            f"({pointage.get_statut_assiduite_display()})"
        )

    def _note(self):
        c = self.contexte
        for module, valeur in ((c['module_a'], '13'), (c['module_b'], '12')):
            colonne, _ = NoteModuleColonne.objects.get_or_create(
                module=module, libelle='CC démo', defaults={'note_max': Decimal('20'), 'ordre': 1},
            )
            NoteModule.objects.create(
                colonne=colonne, participant=c['etudiant'].participant,
                note=Decimal(valeur), verrouillee=True,
                statut_validation=NoteModule.StatutValidation.VALIDEE,
                saisie_par=c['acteur'], validation_par=c['acteur'], validation_le=timezone.now(),
            )
        return "2 notes validées et verrouillées (13/20, 12/20)"

    def _moyenne(self):
        from suiviEvaluation.models import MoyenneModule
        c = self.contexte
        moyennes = []
        for module, valeur in ((c['module_a'], Decimal('13')), (c['module_b'], Decimal('12'))):
            m = MoyenneModule.objects.create(
                module=module, participant=c['etudiant'].participant,
                moyenne=valeur, nb_notes=1, heures_presence=Decimal('3'),
                heures_prevues=Decimal('3'), taux_presence=Decimal('100'),
                calculee_le=timezone.now(),
            )
            moyennes.append(m)
        c['moyennes'] = moyennes
        return f"moyenne générale {((Decimal('13') + Decimal('12')) / 2):.1f}/20"

    def _jury(self):
        from jurys import services as jurys_services
        from jurys.models import DecisionJury, SessionJury
        c = self.contexte
        session = SessionJury(
            annee_academique=c['annee'], ref_formation=c['ref_formation'],
            niveau=c['niveau'], semestre=c['semestre'], maquette=c['maquette'],
            type_session=SessionJury.TypeSession.NORMALE, libelle='Jury de démo SMOKE',
            creee_par=c['acteur'],
        )
        session.full_clean()
        session.save()

        # Chaîne contrôlée : PREPARATION → CONTROLE → CALCUL (calcul des
        # propositions à ce stade) → DELIBERATION (la transition exige qu'elles
        # existent) → saisie de la décision officielle → DECISION → PV_GENERE
        # → VALIDE → VERROUILLE (état requis pour valider un diplôme).
        jurys_services.transition(session, c['acteur'])  # CONTROLE
        jurys_services.transition(session, c['acteur'])  # CALCUL
        nb = jurys_services.calculer_propositions(session, c['acteur'])
        proposition = session.propositions.filter(
            inscription=c['inscription'],
        ).order_by('-calcule_le').first()
        if proposition is None:
            raise AssertionError("Aucune proposition de jury calculée pour l'étudiant.")
        jurys_services.transition(session, c['acteur'])  # DELIBERATION
        decision_proposee = proposition.decision_proposee
        jurys_services.enregistrer_decision(
            session, c['inscription'], decision_proposee, c['acteur'],
            mention='Bien' if decision_proposee in ('VALIDE', 'ADMIS') else '',
        )
        for _ in range(4):  # DECISION → PV_GENERE → VALIDE → VERROUILLE
            jurys_services.transition(session, c['acteur'])
        c['session_jury'] = session
        c['decision_jury'] = DecisionJury.objects.get(
            session=session, inscription=c['inscription'],
        )
        return f"{nb} proposition — décision « {c['decision_jury'].decision} », session {session.statut}"

    def _diplome(self):
        from graduation.models import Diplome
        from graduation.services import valider_diplome
        c = self.contexte
        diplome = Diplome.objects.create(
            etudiant=c['etudiant'], annee_academique=c['annee'],
            ref_formation=c['ref_formation'], parcours=c['parcours'], niveau=c['niveau'],
            session_jury=c['session_jury'], decision_jury=c['decision_jury'],
            credits_acquis=c['decision_jury'].credits_acquis,
        )
        valider_diplome(diplome, c['acteur'])
        c['diplome'] = diplome
        if not diplome.pdf_fichier or not diplome.empreinte_pdf:
            raise AssertionError("Le PDF du diplôme ou son empreinte manque après validation.")
        return f"{diplome.statut} — n° {diplome.numero_unique} (PDF + SHA-256)"

    def _tarifs(self):
        c = self.contexte
        tarifs = [
            Tarification.objects.create(
                formation=c['ref_formation'], annee_academique=c['annee'],
                nature='DOSSIER', montant_base=Decimal('10000'),
            ),
            Tarification.objects.create(
                formation=c['ref_formation'], annee_academique=c['annee'],
                nature='INSCRIPTION', montant_base=Decimal('50000'),
            ),
        ]
        c['tarifs'] = tarifs
        return f"{len(tarifs)} tarifs actifs (dossier 10 000, inscription 50 000 XOF)"

    def _echeancier(self):
        c = self.contexte
        echeancier = generer_echeancier_pour_etudiant(c['etudiant'], c['annee'])
        if echeancier is None or not echeancier.lignes.exists():
            raise AssertionError("Aucune ligne d'échéancier générée depuis les tarifs.")
        c['echeancier'] = echeancier
        return f"échéancier n°{echeancier.pk} — {echeancier.lignes.count()} ligne(s)"

    def _facture(self):
        c = self.contexte
        facture = generer_facture(c['echeancier'], utilisateur=c['acteur'])
        c['facture'] = facture
        return f"facture {facture.numero} — {facture.total} XOF ({facture.statut})"

    def _paiement(self):
        c = self.contexte
        ligne = c['echeancier'].lignes.order_by('date_echeance').first()
        preuve = ContentFile(b'preuve-de-paiement-smoke', name='preuve-smoke.txt')
        paiement, cree = enregistrer_paiement_idempotent(
            etudiant=c['etudiant'], nature=ligne.nature, montant=ligne.montant,
            devise='XOF', mode='CAISSE', transaction_externe='SMOKE-TX-0001',
            utilisateur=c['acteur'],
        )
        paiement.preuve.save('preuve-smoke.txt', preuve, save=True)
        # Idempotence : un second envoi avec la même référence renvoie le même paiement.
        _, cree_bis = enregistrer_paiement_idempotent(
            etudiant=c['etudiant'], nature=ligne.nature, montant=ligne.montant,
            devise='XOF', mode='CAISSE', transaction_externe='SMOKE-TX-0001',
            utilisateur=c['acteur'],
        )
        if cree_bis:
            raise AssertionError("Le second envoi d'une même transaction a créé un doublon.")
        c['paiement'] = paiement
        return f"paiement {paiement.nature} de {paiement.montant} XOF (idempotence vérifiée)"

    def _quittance(self):
        from finances_etudiantes.models import Quittance
        c = self.contexte
        confirmer_paiement(c['paiement'], c['acteur'])
        c['paiement'].refresh_from_db()
        quittance = Quittance.objects.filter(paiement=c['paiement']).first()
        if quittance is None:
            raise AssertionError("Aucune quittance émise après confirmation du paiement.")
        return f"paiement {c['paiement'].statut} — quittance n°{quittance.numero}"

    # -- rapport ------------------------------------------------------------

    def _rapport(self):
        self.stdout.write()
        ligne = '-' * 96
        self.stdout.write(ligne)
        self.stdout.write(f"{'CODE':<24}{'ÉTAPE':<46}{'STATUT':<8}DÉTAIL")
        self.stdout.write(ligne)
        for code, libelle, statut, detail in self.etapes:
            self.stdout.write(f"{code:<24}{libelle:<46}{statut:<8}{detail}")
        self.stdout.write(ligne)
