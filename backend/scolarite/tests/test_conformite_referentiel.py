"""Conformité du référentiel : complétude, notation provisoire, contrôles.

Couvre les mécanismes ajoutés pour traiter les incomplétudes **sans inventer**
de données :

* ``Maquette.controler_completude`` localise les crédits manquants ;
* le clonage conserve la famille officielle des UE ;
* les paramètres de notation restent PROVISOIRES et sont inertes ;
* la commande ``controler_referentiel_injs`` détecte réellement les écarts ;
* une filière sans maquette reste consultable mais **refuse** toute
  inscription pédagogique.
"""

import json
from datetime import date
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from parametres.models import CLES_NOTATION, Parametre
from scolarite.models import ECUE, Maquette, UE
from scolarite.pedagogie_services import PedagogieImpossible, generer_inscriptions_pedagogiques

DONNEES = Path(__file__).resolve().parents[1] / 'data' / 'referentiel_offre_formation.json'


class ReferentielConfigureMixin:
    """Charge le référentiel officiel complet dans la base de test."""

    @classmethod
    def setUpTestData(cls):
        call_command('init_referentiels_lmd', '--annee', '2026-2027',
                     stdout=StringIO())
        call_command('import_referentiel_injs_lmd', stdout=StringIO())
        call_command('qualifier_referentiel_injs_l6', stdout=StringIO())
        call_command('configurer_referentiel_injs', stdout=StringIO())


class CompletudeMaquetteTests(ReferentielConfigureMixin, TestCase):
    """Localisation exacte des crédits manquants, sans invention."""

    def test_maquette_complete(self):
        maquette = Maquette.objects.get(
            ref_formation__filiere_code='F01', niveau__code='L1',
        )
        controle = maquette.controler_completude()
        self.assertTrue(controle['complet'])
        self.assertEqual(controle['credits_documentes'], 60)
        self.assertEqual(controle['credits_attendus'], 60)
        self.assertEqual(controle['credits_manquants'], 0)
        self.assertEqual(controle['semestres_vides'], [])

    def test_ms_m1_incomplet_sur_s8(self):
        """Les 30 crédits manquants sont TOUS situés au semestre 8."""
        maquette = Maquette.objects.get(
            ref_formation__filiere_code='F04', niveau__code='M1',
        )
        controle = maquette.controler_completude()
        self.assertFalse(controle['complet'])
        self.assertEqual(controle['credits_documentes'], 30)
        self.assertEqual(controle['credits_attendus'], 60)
        self.assertEqual(controle['credits_manquants'], 30)
        self.assertEqual(controle['semestres_vides'], [8])
        par_numero = {s['numero']: s for s in controle['semestres']}
        self.assertEqual(par_numero[7]['credits'], 30)
        self.assertEqual(par_numero[7]['ecart'], 0)
        self.assertEqual(par_numero[8]['credits'], 0)
        self.assertEqual(par_numero[8]['ecart'], -30)

    def test_ms_total_270_sur_300(self):
        total = sum(
            maquette.controler_completude()['credits_documentes']
            for maquette in Maquette.objects.filter(
                ref_formation__filiere_code='F04',
            )
        )
        self.assertEqual(total, 270)

    def test_aucune_ue_creee_pour_combler_s8(self):
        """L'incomplétude est constatée, jamais comblée artificiellement."""
        maquette = Maquette.objects.get(
            ref_formation__filiere_code='F04', niveau__code='M1',
        )
        self.assertEqual(
            UE.objects.filter(maquette=maquette, semestre__numero=8).count(), 0,
        )

    def test_les_autres_filieres_sont_completes(self):
        for code in ('F01', 'F02', 'F03'):
            for maquette in Maquette.objects.filter(
                ref_formation__filiere_code=code,
            ):
                self.assertTrue(
                    maquette.controler_completude()['complet'],
                    f'{code} {maquette.niveau.code} devrait être complet.',
                )


class ClonageConserveFamilleTests(ReferentielConfigureMixin, TestCase):
    """Le clonage ne doit pas perdre la famille officielle des UE."""

    def test_clonage_conserve_la_famille(self):
        maquette = Maquette.objects.get(
            ref_formation__filiere_code='F01', niveau__code='L1',
        )
        maquette.statut = Maquette.Statut.VALIDEE
        maquette.save(update_fields=['statut'])
        familles_avant = dict(
            maquette.unites_enseignement.values_list('code', 'famille__libelle')
        )
        self.assertTrue(all(familles_avant.values()), 'Familles attendues non nulles.')

        clone = maquette.cloner()
        familles_apres = dict(
            clone.unites_enseignement.values_list('code', 'famille__libelle')
        )
        self.assertEqual(familles_avant, familles_apres)


class NotationProvisoireTests(TestCase):
    """Les paramètres de notation sont publiés mais jamais appliqués."""

    def test_parametres_crees_en_provsoire(self):
        call_command('parametrer_notation_injs', stdout=StringIO())
        self.assertEqual(
            Parametre.objects.filter(cle__in=CLES_NOTATION).count(),
            len(CLES_NOTATION),
        )
        for cle in CLES_NOTATION:
            self.assertEqual(
                Parametre.objects.get(cle=cle).statut_validation,
                Parametre.StatutValidation.PROVISOIRE,
            )

    def test_valeur_provisoire_non_appliquee(self):
        call_command('parametrer_notation_injs', stdout=StringIO())
        self.assertIsNone(
            Parametre.valeur_institutionnelle('notation.seuil_validation_ue'),
        )

    def test_valeur_validee_appliquee(self):
        call_command('parametrer_notation_injs', stdout=StringIO())
        call_command('parametrer_notation_injs', '--valider', stdout=StringIO())
        self.assertEqual(
            str(Parametre.valeur_institutionnelle('notation.seuil_validation_ue')),
            '10',
        )

    def test_parametre_absent_ne_donne_aucune_valeur(self):
        self.assertIsNone(
            Parametre.valeur_institutionnelle('notation.inexistant'),
        )

    def test_parametre_desactive_non_applique(self):
        parametre = Parametre.objects.create(
            cle='notation.poids_examen', libelle='Poids examen', categorie='scolarite',
            type='decimal', valeur='0.6', valeur_defaut='0.6',
            statut_validation=Parametre.StatutValidation.VALIDE, actif=False,
        )
        self.assertIsNone(Parametre.valeur_institutionnelle('notation.poids_examen'))
        parametre.actif = True
        parametre.save(update_fields=['actif'])
        self.assertEqual(
            str(Parametre.valeur_institutionnelle('notation.poids_examen')), '0.6',
        )

    def test_idempotent(self):
        call_command('parametrer_notation_injs', stdout=StringIO())
        avant = dict(Parametre.objects.filter(cle__in=CLES_NOTATION)
                     .values_list('cle', 'valeur'))
        call_command('parametrer_notation_injs', stdout=StringIO())
        apres = dict(Parametre.objects.filter(cle__in=CLES_NOTATION)
                     .values_list('cle', 'valeur'))
        self.assertEqual(avant, apres)
        self.assertEqual(Parametre.objects.filter(cle__in=CLES_NOTATION).count(), 3)

    def test_valeur_etablissement_preservee_sans_force(self):
        call_command('parametrer_notation_injs', stdout=StringIO())
        parametre = Parametre.objects.get(cle='notation.seuil_validation_ue')
        parametre.valeur = '12'
        parametre.save(update_fields=['valeur'])
        call_command('parametrer_notation_injs', stdout=StringIO())
        parametre.refresh_from_db()
        self.assertEqual(parametre.valeur, '12')

    def test_force_ecrase_la_valeur(self):
        call_command('parametrer_notation_injs', stdout=StringIO())
        parametre = Parametre.objects.get(cle='notation.seuil_validation_ue')
        parametre.valeur = '12'
        parametre.save(update_fields=['valeur'])
        call_command('parametrer_notation_injs', '--force', stdout=StringIO())
        parametre.refresh_from_db()
        self.assertEqual(parametre.valeur, '10')

    def test_dry_run_n_ecrit_rien(self):
        call_command('parametrer_notation_injs', '--dry-run', stdout=StringIO())
        self.assertEqual(Parametre.objects.filter(cle__in=CLES_NOTATION).count(), 0)


class SeuilAfficheTests(TestCase):
    """Aucun seuil n'est inventé à l'affichage."""

    def test_seuil_absent_affiche_non_parametre(self):
        from presences.notes_exports import _seuil_affiche

        self.assertEqual(_seuil_affiche(None), 'non paramétré')
        self.assertEqual(_seuil_affiche(''), 'non paramétré')

    def test_seuil_present_affiche(self):
        from presences.notes_exports import _seuil_affiche

        self.assertEqual(_seuil_affiche('10.00'), '10.00/20')


class ControleReferentielTests(ReferentielConfigureMixin, TestCase):
    """La commande de contrôle détecte réellement les écarts."""

    def _executer(self, *args):
        sortie = StringIO()
        call_command('controler_referentiel_injs', *args, stdout=sortie)
        return sortie.getvalue()

    def test_source_presente_et_coherente(self):
        self.assertTrue(DONNEES.is_file())
        donnees = json.loads(DONNEES.read_text(encoding='utf-8'))
        self.assertEqual(
            sum(len(l) for s in donnees['maquettes'].values() for l in s.values()),
            323,
        )

    def test_controle_sans_anomalie(self):
        sortie = self._executer('--strict')
        self.assertIn('Aucune anomalie détectée', sortie)
        self.assertIn('323 source / 323 base', sortie)
        self.assertIn('397 source / 397 base', sortie)

    def test_controle_signale_les_34_elements(self):
        sortie = self._executer()
        self.assertIn('34 éléments', sortie)

    def test_controle_signale_ms_s8(self):
        sortie = self._executer()
        self.assertIn('F04 M1 : 30/60 ECTS', sortie)
        self.assertIn('[8]', sortie)

    def test_controle_signale_f05_a_f08(self):
        sortie = self._executer()
        for code in ('F05', 'F06', 'F07', 'F08'):
            self.assertIn(code, sortie)

    def test_controle_sortie_json(self):
        sortie = self._executer('--json')
        donnees = json.loads(sortie)
        self.assertTrue(donnees['conforme'])
        self.assertEqual(donnees['resume']['ue_source'], 323)
        self.assertEqual(donnees['resume']['hors_lmd']['total'], 34)

    def test_controle_detecte_une_ue_orpheline(self):
        """Une incohérence introduite est bien détectée (le contrôle n'est pas vide)."""
        maquette = Maquette.objects.first()
        UE.objects.create(
            maquette=maquette, semestre=maquette.unites_enseignement.first().semestre,
            code='TEST-ORPHELINE', intitule='UE de test', credits=1,
        )
        sortie = self._executer()
        self.assertIn('[NB_UE]', sortie)
        self.assertIn('324', sortie)

    def test_controle_strict_echoue_sur_anomalie(self):
        maquette = Maquette.objects.first()
        UE.objects.create(
            maquette=maquette, semestre=maquette.unites_enseignement.first().semestre,
            code='TEST-STRICT', intitule='UE de test', credits=1,
        )
        with self.assertRaises(CommandError):
            self._executer('--strict')


class FilieresSansMaquetteTests(ReferentielConfigureMixin, TestCase):
    """F05–F08 : consultables, mais aucune inscription pédagogique possible."""

    def test_filieres_consultables(self):
        from formations.models import RefFormation

        for code in ('F05', 'F06', 'F07', 'F08'):
            self.assertTrue(
                RefFormation.objects.filter(
                    filiere_code=code,
                    perimetre=RefFormation.Perimetre.INJS,
                ).exists(),
                f'{code} doit rester enregistrée et consultable.',
            )

    def test_aucune_maquette_pour_f05_a_f08(self):
        self.assertEqual(
            Maquette.objects.filter(
                ref_formation__filiere_code__in=['F05', 'F06', 'F07', 'F08'],
            ).count(),
            0,
        )

    def test_inscription_pedagogique_refusee_sans_maquette(self):
        """Une inscription pédagogique impossible est refusée explicitement."""
        from datetime import date, datetime

        from django.utils import timezone

        from formations.models import Participant, RefFormation
        from scolarite.models import (
            AnneeAcademique,
            DossierEtudiant,
            InscriptionAdministrative,
            Niveau,
        )

        annee, _ = AnneeAcademique.objects.get_or_create(
            libelle='2026-2027',
            defaults={
                'date_debut': date(2026, 10, 1),
                'date_fin': date(2027, 9, 30),
                'courante': True,
            },
        )
        filiere = RefFormation.objects.get(filiere_code='F05')
        participant = Participant.objects.create(
            matricule='INJS26-9001', nom='Test', prenom='F05',
        )
        dossier = DossierEtudiant.objects.create(participant=participant)
        inscription = InscriptionAdministrative.objects.create(
            etudiant=dossier,
            annee_academique=annee,
            ref_formation=filiere,
            niveau=Niveau.objects.get(code='L1'),
            statut=InscriptionAdministrative.Statut.VALIDEE,
            date_validation=timezone.make_aware(datetime(2026, 10, 1, 12, 0)),
        )
        with self.assertRaises(PedagogieImpossible) as contexte:
            generer_inscriptions_pedagogiques(inscription)
        self.assertIn('maquette', str(contexte.exception).lower())
