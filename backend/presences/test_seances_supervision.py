"""Tests du bloc « Séances en direct » (supervision LMD des séances).

Couvre les règles métier du modèle réel, sans jamais fabriquer de données qui
contrediraient ``edts.AffectationCreneau`` / ``presences.Pointage`` :

- statut de séance déduit des **horaires** (jamais du nombre de pointages) ;
- effectif attendu issu des membres actifs du **groupe** ;
- catégories d'assiduité réellement stockées, sans regroupement forcé ;
- absence de double comptage (participants hors périmètre, lignes multiples) ;
- ``NULL``Jamais transformé en ``0`` (effectif, taux) ;
- séance sans présence, séance annulée, groupe sans participant ;
- RBAC : périmètre de lecture par rôle ;
- aucune écriture depuis la console (endpoint en lecture seule) ;
- absence de référence CPFAE / Sygepcpfae.

Les horaires sont ancrés sur l'heure courante pour que la fenêtre « en cours »
soit réellement ouverte pendant l'exécution (même convention que
``presences.test_seances_edt``).
"""
from datetime import time, timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from authentication.models import User
from edts.models import AffectationCreneau, CreneauTemplate, EmploiDuTemps
from formations.models import Participant, QRToken, RefFormation, RefSalle, RefSite
from presences import seances_supervision as supervision
from presences.models import Pointage
from scolarite.models import (
    AffectationGroupe, AffectationPedagogique, AnneeAcademique, DossierEtudiant,
    ECUE, Groupe, InscriptionAdministrative, Maquette, Niveau, Parcours,
    StatutEtudiant, UE,
)

JOURS = ['LUNDI', 'MARDI', 'MERCREDI', 'JEUDI', 'VENDREDI', 'SAMEDI', 'DIMANCHE']

URL_SUPERVISION = '/api/presences/seances-edt/supervision/'


def _pointage(participant, affectation, date, **kwargs):
    """Pointage rattaché à une séance LMD (QR ou émargement manuel)."""
    defauts = {
        'timestamp_entree': timezone.now(),
        'device_id': 'MOBILE-001',
    }
    defauts.update(kwargs)
    return Pointage.objects.create(
        participant=participant, seance_edt=affectation, date_journee=date, **defauts)


class BaseSupervision(TestCase):
    """Fixture : une séance en cours aujourd'hui, son groupe et 3 membres."""

    @classmethod
    def setUpTestData(cls):
        cls.aujourdhui = timezone.localdate()
        maintenant = timezone.localtime(timezone.now())
        cls.debut_time = (maintenant - timedelta(minutes=5)).time()
        cls.fin_time = (maintenant + timedelta(minutes=55)).time()

        cls.annee = AnneeAcademique.objects.create(
            libelle='2026-2027', date_debut=cls.aujourdhui - timedelta(weeks=3),
            date_fin=cls.aujourdhui + timedelta(weeks=40), courante=True,
        )
        cls.niveau = Niveau.objects.create(code='L1', libelle='Licence 1', ordre=1)
        cls.parcours = Parcours.objects.create(ref_formation=None, code='EPS',
                                                intitule='EPS') if False else None
        cls.formation = RefFormation.objects.create(intitule='Licence STAPS')
        cls.parcours = Parcours.objects.create(ref_formation=cls.formation, code='EPS',
                                                intitule='EPS')
        cls.groupe = Groupe.objects.create(
            annee_academique=cls.annee, niveau=cls.niveau, ref_formation=cls.formation,
            parcours=cls.parcours, nom='L1-G1', capacite_max=40)
        cls.site = RefSite.objects.create(nom='INJS Marcory')
        cls.salle = RefSalle.objects.create(site=cls.site, nom='Amphi 1')

        cls.template = CreneauTemplate.objects.create(
            jour=JOURS[cls.aujourdhui.weekday()], heure_debut=cls.debut_time,
            heure_fin=cls.fin_time)
        cls.edt = EmploiDuTemps.objects.create(
            annee_academique=cls.annee, population_type='ANNEE', population_id=0,
            statut='PUBLIE', semaine_debut=1, semaine_fin=10,
            rentree=cls.annee.date_debut)
        cls.affectation = AffectationCreneau.objects.create(
            emploi_du_temps=cls.edt, creneau_template=cls.template,
            semaine_debut=1, semaine_fin=10, groupe=cls.groupe,
            formation=cls.formation, salle=cls.salle, salle_nom=cls.salle.nom,
            enseignant_nom='Awa Traoré', intitule='Physique appliquée')

        # Trois membres du groupe : effectif attendu = 3.
        cls.statut_actif = StatutEtudiant.objects.create(code='ACTIF-SUP',
                                                         libelle='Actif')
        cls.participants = []
        for index in range(3):
            participant = Participant.objects.create(
                matricule=f'SUP{index:03d}', nom=f'Participant{index}',
                prenom=f'Prenom{index}')
            dossier = DossierEtudiant.objects.create(participant=participant,
                                                     statut=cls.statut_actif)
            inscription = InscriptionAdministrative.objects.create(
                etudiant=dossier, annee_academique=cls.annee, niveau=cls.niveau,
                ref_formation=cls.formation,
                statut=InscriptionAdministrative.Statut.VALIDEE,
                statut_etudiant=cls.statut_actif)
            AffectationGroupe.objects.create(inscription=inscription, groupe=cls.groupe,
                                             active=True)
            cls.participants.append(participant)

        cls.admin = User.objects.create_user(username='sup-admin', password='x',
                                             role='ADMIN')
        cls.enseignant = User.objects.create_user(username='sup-ens', password='x',
                                                  role='ENCADRANT')

    def ligne(self, seance_id=None):
        """Ligne de séance du payload de supervision (par défaut, la nôtre)."""
        donnees = supervision.supervision_seances(self.admin, self.aujourdhui)
        cible = seance_id or self.affectation.id
        return next(l for l in donnees['seances'] if l['id'] == cible)


class StatutSeanceTests(BaseSupervision):
    """Le statut vient des horaires, jamais du nombre de pointages."""

    def test_seance_en_cours_sans_aucune_presence(self):
        """Une séance vide est « en cours » : c'est l'horaire qui le dit."""
        ligne = self.ligne()
        self.assertEqual(ligne['statut'], 'EN_COURS')
        self.assertTrue(ligne['en_direct'])
        self.assertEqual(ligne['presences']['presents'], 0)

    def test_statut_a_venir_puis_terminee(self):
        affectation = self.affectation
        debut, fin = supervision.service.horodatages(affectation, self.aujourdhui)
        self.assertEqual(
            supervision.statut_seance(affectation, self.aujourdhui,
                                      debut - timedelta(minutes=1)),
            'A_VENIR')
        self.assertEqual(
            supervision.statut_seance(affectation, self.aujourdhui,
                                      fin + timedelta(minutes=1)),
            'TERMINEE')
        self.assertEqual(
            supervision.statut_seance(affectation, self.aujourdhui, timezone.now()),
            'EN_COURS')

    def test_seance_annulee_reste_visible_avec_son_statut(self):
        """``actif=False`` = annulation logique : elle ne disparaît pas."""
        self.affectation.actif = False
        self.affectation.save(update_fields=['actif'])
        ligne = self.ligne()
        self.assertEqual(ligne['statut'], 'ANNULEE')
        self.assertFalse(ligne['en_direct'])

    def test_seance_absente_un_autre_jour(self):
        """Une séance du jour n'est pas listée pour une date sans occurrence."""
        donnees = supervision.supervision_seances(
            self.admin, self.aujourdhui + timedelta(days=1))
        self.assertEqual(donnees['seances'], [])
        self.assertEqual(donnees['resume']['seances_total'], 0)


class EffectifAttenduTests(BaseSupervision):
    """L'effectif vient du groupe réel ; ``None`` quand il est inconnu."""

    def test_effectif_attendu_vient_du_groupe(self):
        self.assertEqual(self.ligne()['effectif_attendu'], 3)

    def test_affectation_de_groupe_inactive_hors_effectif(self):
        AffectationGroupe.objects.update(active=False)
        self.assertEqual(self.ligne()['effectif_attendu'], 0)

    def test_groupe_vide_donne_un_effectif_connu_a_zero(self):
        AffectationGroupe.objects.all().delete()
        ligne = self.ligne()
        self.assertEqual(ligne['effectif_attendu'], 0)
        # 0 attendus = dénominateur invalide → pas de taux, pas de 0 %.
        self.assertIsNone(ligne['taux_presence'])

    def test_seance_sans_groupe_donne_null_et_pas_zero(self):
        self.affectation.groupe = None
        self.affectation.save(update_fields=['groupe'])
        ligne = self.ligne()
        self.assertIsNone(ligne['effectif_attendu'])
        self.assertIsNone(ligne['non_pointes'])
        self.assertIsNone(ligne['taux_presence'])

    def test_anomalie_comptee_quand_effectif_inconnu(self):
        self.affectation.groupe = None
        self.affectation.save(update_fields=['groupe'])
        donnees = supervision.supervision_seances(self.admin, self.aujourdhui)
        self.assertEqual(donnees['resume']['anomalies'], 1)

class CategoriesPresenceTests(BaseSupervision):
    """Les catégories suivent ``Pointage.statut_assiduite`` sans regroupement."""

    def test_presents_absents_justifies_et_dispenses(self):
        _pointage(self.participants[0], self.affectation, self.aujourdhui,
                  statut=Pointage.Statut.TERMINE,
                  statut_assiduite=Pointage.StatutAssiduite.PRESENT,
                  timestamp_sortie=timezone.now())
        _pointage(self.participants[1], self.affectation, self.aujourdhui,
                  statut=Pointage.Statut.ABSENT_NON_BADGE,
                  statut_assiduite=Pointage.StatutAssiduite.ABSENCE_JUSTIFIEE)
        _pointage(self.participants[2], self.affectation, self.aujourdhui,
                  statut=Pointage.Statut.ABSENT_NON_BADGE,
                  statut_assiduite=Pointage.StatutAssiduite.EXCUSE)
        presences = self.ligne()['presences']
        self.assertEqual(presences['presents'], 1)
        self.assertEqual(presences['absents_justifies'], 1)
        self.assertEqual(presences['dispenses'], 1)
        self.assertEqual(presences['absents_injustifies'], 0)

    def test_absence_non_justifiee_reste_distincte(self):
        _pointage(self.participants[0], self.affectation, self.aujourdhui,
                  statut=Pointage.Statut.ABSENT_NON_BADGE,
                  statut_assiduite=Pointage.StatutAssiduite.ABSENT)
        presences = self.ligne()['presences']
        self.assertEqual(presences['absents_injustifies'], 1)
        self.assertEqual(presences['absents_justifies'], 0)

    def test_statut_assiduite_null_repli_sur_le_mapping_du_modele(self):
        _pointage(self.participants[0], self.affectation, self.aujourdhui,
                  statut=Pointage.Statut.TERMINE, statut_assiduite=None,
                  timestamp_sortie=timezone.now())
        self.assertEqual(self.ligne()['presences']['presents'], 1)

    def test_non_renseigne_ne_compte_pas_comme_une_absence(self):
        _pointage(self.participants[0], self.affectation, self.aujourdhui,
                  statut=Pointage.Statut.HORS_LIGNE_SUSPECT,
                  statut_assiduite=Pointage.StatutAssiduite.NON_RENSEIGNE)
        presences = self.ligne()['presences']
        self.assertEqual(presences['non_renseignes'], 1)
        self.assertEqual(presences['absents_injustifies'], 0)
        self.assertEqual(presences['absents_justifies'], 0)

    def test_non_pointes_complets_sur_seance_sans_presence(self):
        ligne = self.ligne()
        self.assertEqual(ligne['presences']['presents'], 0)
        self.assertEqual(ligne['non_pointes'], 3)
        self.assertEqual(ligne['taux_presence'], 0.0)

    def test_taux_calcule_sur_l_effectif_reel(self):
        for participant in self.participants[:2]:
            _pointage(participant, self.affectation, self.aujourdhui,
                      statut=Pointage.Statut.TERMINE,
                      statut_assiduite=Pointage.StatutAssiduite.PRESENT,
                      timestamp_sortie=timezone.now())
        ligne = self.ligne()
        self.assertEqual(ligne['presences']['presents'], 2)
        self.assertEqual(ligne['non_pointes'], 1)
        self.assertAlmostEqual(ligne['taux_presence'], round(2 / 3, 4), places=4)

    def test_sources_qr_et_manuelle_exposees(self):
        _pointage(self.participants[0], self.affectation, self.aujourdhui,
                  statut=Pointage.Statut.EN_COURS, device_id='MOBILE-001')
        _pointage(self.participants[1], self.affectation, self.aujourdhui,
                  statut=Pointage.Statut.TERMINE, device_id='EMARGEMENT_MANUEL',
                  timestamp_sortie=timezone.now())
        presences = self.ligne()['presences']
        self.assertEqual(presences['source_qr'], 1)
        self.assertEqual(presences['source_manuelle'], 1)


class PasDeDoubleComptageTests(BaseSupervision):
    """Un participant n'est compté qu'une fois, et seulement dans son groupe."""

    def test_plusieurs_lignes_pour_un_meme_participant(self):
        entree = timezone.now() - timedelta(minutes=30)
        _pointage(self.participants[0], self.affectation, self.aujourdhui,
                  statut=Pointage.Statut.EN_COURS, timestamp_entree=entree)
        # Correction manuelle postérieure : la dernière ligne l'emporte.
        _pointage(self.participants[0], self.affectation, self.aujourdhui,
                  statut=Pointage.Statut.TERMINE, device_id='EMARGEMENT_MANUEL',
                  timestamp_entree=entree + timedelta(minutes=10),
                  timestamp_sortie=timezone.now())
        ligne = self.ligne()
        self.assertEqual(ligne['presences']['presents'], 1)
        self.assertEqual(ligne['presences']['source_manuelle'], 1)
        self.assertEqual(ligne['presences']['source_qr'], 0)

    def test_presence_hors_perimetre_non_imputee_a_la_seance(self):
        """Un participant d'un autre groupe n'entre pas dans les statistiques."""
        autre = Participant.objects.create(matricule='HORS01', nom='Etranger',
                                            prenom='Hors')
        _pointage(autre, self.affectation, self.aujourdhui,
                  statut=Pointage.Statut.TERMINE,
                  statut_assiduite=Pointage.StatutAssiduite.PRESENT,
                  timestamp_sortie=timezone.now())
        ligne = self.ligne()
        self.assertEqual(ligne['presences']['presents'], 0)
        self.assertEqual(ligne['presences']['presences_hors_perimetre'], 1)
        # L'effectif attendu, lui, ne bouge pas : il vient du groupe.
        self.assertEqual(ligne['effectif_attendu'], 3)

    def test_pointage_d_un_autre_jour_ignore(self):
        _pointage(self.participants[0], self.affectation,
                  self.aujourdhui - timedelta(days=1),
                  statut=Pointage.Statut.TERMINE,
                  timestamp_sortie=timezone.now())
        self.assertEqual(self.ligne()['presences']['presents'], 0)

    def test_pointage_sans_participant_ignore(self):
        Pointage.objects.create(
            participant=None, seance_edt=self.affectation,
            date_journee=self.aujourdhui, timestamp_entree=timezone.now(),
            statut=Pointage.Statut.EN_COURS)
        self.assertEqual(self.ligne()['presences']['presents'], 0)


class ContextePedagogiqueTests(BaseSupervision):
    """La chaîne LMD est lue par clés étrangères, jamais par libellé."""

    def _rattacher(self):
        """Rattache la séance à une affectation pédagogique complète."""
        semestre = self._semestre()
        # La maquette doit être modifiable pour accueillir UE puis ECUE :
        # le modèle verrouille une maquette ACTIVE (règle d'immuabilité LMD).
        maquette = Maquette.objects.create(
            annee_academique=self.annee, ref_formation=self.formation,
            parcours=self.parcours, niveau=self.niveau, libelle='Maquette test',
            version=1, statut=Maquette.Statut.BROUILLON)
        ue = UE.objects.create(maquette=maquette, semestre=semestre, code='UE1',
                               intitule='Physique', credits=4)
        ecue = ECUE.objects.create(ue=ue, code='ECUE-PHY',
                                   intitule='Physique appliquée')
        maquette.statut = Maquette.Statut.ACTIVE
        maquette.save(update_fields=['statut'])
        from formations.models import Formateur
        formateur = Formateur.objects.create(numerobadge='FB-001', nom='Traoré',
                                             prenom='Awa')
        affectation_pedagogique = AffectationPedagogique.objects.create(
            annee_academique=self.annee, ref_formation=self.formation,
            parcours=self.parcours, niveau=self.niveau, semestre=semestre, ue=ue,
            ecue=ecue, groupe=self.groupe, enseignant=formateur,
            type_enseignement=AffectationPedagogique.TypeEnseignement.CM)
        self.affectation.affectation_pedagogique = affectation_pedagogique
        self.affectation.save(update_fields=['affectation_pedagogique'])

    def _semestre(self):
        from scolarite.models import Semestre
        return Semestre.objects.create(niveau=self.niveau, numero=1,
                                       libelle='Semestre 1')

    def test_chaine_lmd_exposee_via_l_affectation_pedagogique(self):
        self._rattacher()
        ligne = self.ligne()
        self.assertEqual(ligne['ecue_code'], 'ECUE-PHY')
        self.assertEqual(ligne['ue_code'], 'UE1')
        self.assertEqual(ligne['parcours_libelle'], 'EPS')
        self.assertEqual(ligne['formation_libelle'], 'Licence STAPS')
        self.assertEqual(ligne['groupe_libelle'], 'L1-G1')

    def test_sans_rattachement_ecue_et_ue_restent_null(self):
        ligne = self.ligne()
        self.assertIsNone(ligne['affectation_pedagogique_id'])
        self.assertIsNone(ligne['ecue_code'])
        self.assertIsNone(ligne['ue_code'])
        self.assertIsNone(ligne['ue_libelle'])

    def test_enseignant_et_saille_prevenus(self):
        ligne = self.ligne()
        self.assertEqual(ligne['salle_libelle'], 'Amphi 1')
        self.assertEqual(ligne['libelle'], 'Awa Traoré')

    def test_absences_de_libelles_chez_un_enseignant_sans_formateur(self):
        self.affectation.enseignant_nom = ''
        self.affectation.save(update_fields=['enseignant_nom'])
        self.assertIsNone(self.ligne()['libelle'])

        _pointage(self.participants[0], self.affectation, self.aujourdhui,
                  statut=Pointage.Statut.EN_COURS, device_id='MOBILE-001')
        _pointage(self.participants[1], self.affectation, self.aujourdhui,
                  statut=Pointage.Statut.TERMINE, device_id='EMARGEMENT_MANUEL',
                  timestamp_sortie=timezone.now())
        presences = self.ligne()['presences']
        self.assertEqual(presences['source_qr'], 1)
        self.assertEqual(presences['source_manuelle'], 1)

class ApiSupervisionTests(BaseSupervision):
    """Endpoint en lecture seule : RBAC, filtres, contrat et absence d'écriture."""

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def test_payload_attendue(self):
        reponse = self.client.get(URL_SUPERVISION)
        self.assertEqual(reponse.status_code, 200)
        donnees = reponse.json()
        for cle in ('date', 'genere_le', 'resume', 'seances'):
            self.assertIn(cle, donnees)
        self.assertEqual(len(donnees['seances']), 1)
        self.assertEqual(donnees['seances'][0]['id'], self.affectation.id)

    def test_anonyme_refuse(self):
        self.client.force_authenticate(user=None)
        self.assertIn(self.client.get(URL_SUPERVISION).status_code, (401, 403))

    def test_endpoint_en_lecture_seule(self):
        """Aucun verbe d'écriture : la console de supervision n'écrit jamais."""
        reponse = self.client.post(URL_SUPERVISION, {}, format='json')
        self.assertEqual(reponse.status_code, 405)
        self.assertEqual(self.client.put(URL_SUPERVISION, {}).status_code, 405)
        self.assertEqual(self.client.delete(URL_SUPERVISION).status_code, 405)

    def test_aucune_presence_n_est_creee_par_la_consultation(self):
        avant = Pointage.objects.count()
        jetons = QRToken.objects.count()
        self.client.get(URL_SUPERVISION)
        self.client.get(URL_SUPERVISION, {'statut': 'EN_COURS'})
        self.assertEqual(Pointage.objects.count(), avant)
        self.assertEqual(QRToken.objects.count(), jetons)

    def test_date_invalide_refusee(self):
        reponse = self.client.get(URL_SUPERVISION, {'date': 'hier'})
        self.assertEqual(reponse.status_code, 400)
        self.assertIn('date', reponse.json()['detail'])

    def test_statut_inconnu_refuse(self):
        reponse = self.client.get(URL_SUPERVISION, {'statut': 'N_IMPORTE_QUOI'})
        self.assertEqual(reponse.status_code, 400)
        self.assertIn('Statut', reponse.json()['detail'])

    def test_filtre_par_groupe_applique_au_serveur(self):
        vide = self.client.get(URL_SUPERVISION, {'groupe_id': 99999})
        self.assertEqual(vide.status_code, 200)
        self.assertEqual(vide.json()['seances'], [])
        pleine = self.client.get(URL_SUPERVISION, {'groupe_id': self.groupe.id})
        self.assertEqual(len(pleine.json()['seances']), 1)

    def test_filtre_par_statut_applique_au_serveur(self):
        vide = self.client.get(URL_SUPERVISION, {'statut': 'TERMINEE'})
        self.assertEqual(vide.json()['seances'], [])
        pleine = self.client.get(URL_SUPERVISION, {'statut': 'EN_COURS'})
        self.assertEqual(len(pleine.json()['seances']), 1)

    def test_filtres_illisible_non_bloquants(self):
        """Un filtre hors périmètre ramène une liste vide, pas une erreur."""
        reponse = self.client.get(URL_SUPERVISION, {'formation_id': 'abc',
                                                    'groupe_id': ''})
        self.assertEqual(reponse.status_code, 200)

    def test_enseignant_ne_voit_que_ses_seances(self):
        self.affectation.enseignant_id = self.enseignant.id
        self.affectation.save(update_fields=['enseignant_id'])
        donnees = supervision.supervision_seances(self.enseignant, self.aujourdhui)
        self.assertEqual(len(donnees['seances']), 1)
        # Un compte sans rattachement ne supervise rien.
        autre = User.objects.create_user(username='sup-autre', password='x',
                                         role='ENCADRANT')
        vide = supervision.supervision_seances(autre, self.aujourdhui)
        self.assertEqual(vide['seances'], [])

    def test_aucune_reference_cpfae_dans_le_perimetre(self):
        """Garde-fou §18 : le code du nouveau périmètre reste INJS-LMD.

        On inspecte le **code exécutable** (constantes de module et noms
        d'attributs), pas les docstrings : celles-ci *interdisent* explicitement
        ces référentiels, les mentionner y est donc légitime.
        """
        import ast as _ast
        import inspect

        from presences import seances_edt_api, seances_supervision as service

        for module in (service, seances_edt_api):
            arbre = _ast.parse(inspect.getsource(module))
            # On retire les docstrings : y citer un référentiel interdit est
            # la façon normale de dire « ne l'utilise pas ».
            for noeud in _ast.walk(arbre):
                if isinstance(noeud, (_ast.Module, _ast.FunctionDef,
                                       _ast.AsyncFunctionDef, _ast.ClassDef)):
                    if (noeud.body
                            and isinstance(noeud.body[0], _ast.Expr)
                            and isinstance(noeud.body[0].value, _ast.Constant)
                            and isinstance(noeud.body[0].value.value, str)):
                        noeud.body = noeud.body[1:] or [_ast.Pass()]
            noms = []
            for noeud in _ast.walk(arbre):
                if isinstance(noeud, _ast.Constant) and isinstance(noeud.value, str):
                    noms.append(noeud.value)
                elif isinstance(noeud, _ast.Name):
                    noms.append(noeud.id)
                elif isinstance(noeud, _ast.Attribute):
                    noms.append(noeud.attr)
            code = ' '.join(noms).lower()
            for terme in ('cpfae', 'sygepcpfae'):
                self.assertNotIn(terme, code,
                                 f'{module.__name__} ne doit pas référencer {terme}')
