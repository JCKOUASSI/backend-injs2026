"""Identité institutionnelle réellement imprimée sur les documents exportés.

Origine — plusieurs exports portaient encore l'en-tête, et parfois l'adresse
postale, du CPFAE (établissement auquel l'application ne se destine plus). La
correction a été centralisée dans :mod:`core.institution`, mais aucun test ne
vérifiait qu'elle atteint réellement le fichier produit : c'est précisément le
type d'écart (code corrigé, document inchangé) qui échappe à une revue humaine.

Ce module produit donc de vrais fichiers — PDF et Excel — et inspecte leur
contenu binaire :

* le PDF est décompressé (flux ``FlateDecode``) pour retrouver le texte tracé ;
* l'Excel est relu avec ``openpyxl``.

Aucune donnée institutionnelle n'est inventée : les fixtures sont des objets de
test, et l'adresse postale n'est vérifiée que si l'exploitant l'a configurée.
"""
import os
import re
import subprocess
import sys
import zlib
from datetime import time
from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.test import TestCase, override_settings
from django.utils import timezone
from openpyxl import load_workbook

from core import institution
from formations.models import (
    Formation,
    Module,
    ModuleParticipant,
    Participant,
    SessionModule,
)
from exports.participants_list_export import _HEADER_LINES
from statistiques.point_journalier import compute_point_journalier
from statistiques.point_journalier_exports import _filter_tableaux, export_pdf, export_excel


def texte_pdf(contenu: bytes) -> bytes:
    """Texte approximatif d'un PDF : concaténation des flux décodés.

    ReportLab encode les flux en ``ASCII85Decode`` puis ``FlateDecode`` : on
    applique les deux filtres, et on retombe sur le flux brut s'il n'est pas
    compressé. Suffisant pour chercher un libellé, sans dépendance PDF.
    """
    import base64

    morceaux = []
    for flux in re.findall(rb'stream\r?\n(.*?)endstream', contenu, re.S):
        brut = flux.strip()
        for decodeur in (
            lambda f: zlib.decompress(base64.a85decode(f, adobe=True)),
            lambda f: zlib.decompress(f),
            lambda f: base64.a85decode(f, adobe=True),
        ):
            try:
                morceaux.append(decodeur(brut))
                break
            except Exception:  # noqa: BLE001 - on essaie le filtre suivant
                continue
        else:
            morceaux.append(brut)
    return b'\n'.join(morceaux)


class IdentiteInstitutionnelleTests(TestCase):
    """Le nom officiel de l'INJS, et jamais celui du CPFAE."""

    def test_entete_porte_le_nom_officiel(self):
        lignes = institution.lignes_entete()
        assert institution.NOM_OFFICIEL in lignes
        assert any('Jeunesse' in ligne for ligne in lignes)
        assert institution.MINISTERE_TUTELLE in lignes

    def test_entete_ne_porte_aucun_sigle_historique(self):
        for ligne in institution.lignes_entete(avec_ufr=True):
            assert 'CPFAE' not in ligne.upper()
            assert 'SYGEP' not in ligne.upper()

    def test_pied_de_page_sans_adresse_inventee(self):
        with override_settings(INJS_ADRESSE_OFFICIELLE=''):
            pied = institution.pied_de_page()
        assert pied == 'Institut National de la Jeunesse et des Sports (INJS) — ABIDJAN'

    @override_settings(INJS_ADRESSE_OFFICIELLE='01 BP 1234 Abidjan 01')
    def test_pied_de_page_imprime_l_adresse_configuree(self):
        assert '01 BP 1234 Abidjan 01' in institution.pied_de_page()

    def test_libelles_de_roles_sans_sigle_historique(self):
        """Les libellés de rôle alimentent l'interface : aucun sigle hérité."""
        from authentication.role_groups import ROLE_LABELS

        for code, libelle in ROLE_LABELS.items():
            texte = str(libelle).upper()
            for sigle in ('CPFAE', 'SYGEP', 'DFRC'):
                assert sigle not in texte, f'rôle {code} : libellé « {libelle} »'

    def test_liste_de_classe_porte_l_entete_injs(self):
        lignes = list(_HEADER_LINES)
        assert any('Institut National de la Jeunesse' in ligne for ligne in lignes)
        assert not any('CPFAE' in ligne.upper() for ligne in lignes)

class ConfigurationIdentiteTests(TestCase):
    """L'adresse officielle doit être réglable SANS modification de code.

    Le module `core/institution` documentait `INJS_ADRESSE_OFFICIELLE` et
    `INJS_NOM_OFFICIEL` comme variables d'environnement, mais `config.settings`
    ne les lisait pas : la variable n'avait donc aucun effet, et l'adresse
    restait vide quoi qu'on fasse. Ce test lance un vrai processus Django avec
    les variables posées, pour vérifier le câblage de bout en bout.
    """

    def test_reglages_declares(self):
        self.assertTrue(hasattr(settings, 'INJS_ADRESSE_OFFICIELLE'))
        self.assertTrue(hasattr(settings, 'INJS_NOM_OFFICIEL'))

    def test_nom_vide_retombe_sur_le_nom_officiel(self):
        with override_settings(INJS_NOM_OFFICIEL=''):
            self.assertEqual(institution.nom_etablissement(), institution.NOM_OFFICIEL)
        with override_settings(INJS_NOM_OFFICIEL='   '):
            self.assertEqual(institution.nom_etablissement(), institution.NOM_OFFICIEL)

    def test_variables_d_environnement_honorees(self):
        base = Path(settings.BASE_DIR)
        env = {
            **os.environ,
            'INJS_ADRESSE_OFFICIELLE': '01 BP 4242 Abidjan 42',
            'INJS_NOM_OFFICIEL': 'Institut National de la Jeunesse et des Sports',
            'DJANGO_SETTINGS_MODULE': os.environ.get(
                'DJANGO_SETTINGS_MODULE', 'config.settings'),
        }
        resultat = subprocess.run(
            [sys.executable, 'manage.py', 'shell', '-c',
             'from core.institution import pied_de_page; print(pied_de_page())'],
            cwd=str(base), env=env, capture_output=True, text=True, timeout=180,
        )
        self.assertEqual(resultat.returncode, 0, resultat.stderr[-800:])
        self.assertIn('01 BP 4242 Abidjan 42', resultat.stdout)
        self.assertIn('Institut National de la Jeunesse et des Sports', resultat.stdout)


class DocumentsGeneresTests(TestCase):
    """Le fichier réellement produit porte l'identité INJS."""

    def setUp(self):
        self.formation = Formation.objects.create(
            formation='Formation Identité Documentaire',
        )
        self.jour = timezone.localdate()
        self.participant = Participant.objects.create(
            matricule='IDD-001', nom='Identite', prenom='Test', categorie='A',
        )
        self.module = Module.objects.create(
            formation=self.formation, intitule='DEONTOLOGIE', grade='A4',
            groupe='GROUPE 10', salle='SALLE A',
        )
        ModuleParticipant.objects.create(module=self.module, participant=self.participant)
        SessionModule.objects.create(
            module=self.module,
            date_journee=self.jour,
            numero=1,
            intitule='Matin',
            heure_debut_prevue=time(8, 0),
            heure_fin_prevue=time(12, 0),
        )

    def _tableaux(self):
        data = compute_point_journalier(
            annee=self.jour.year,
            mois=self.jour.month,
            categorie='A',
            formation_id=self.formation.id,
            jour=self.jour.isoformat(),
        )
        return _filter_tableaux(
            data,
            formation_id=self.formation.id,
            categorie='A',
            jour=self.jour.isoformat(),
        )

    def test_excel_point_journalier_sans_sigle_historique(self):
        tableaux = self._tableaux()
        self.assertTrue(tableaux, 'fixture sans tableau : test non concluant')
        buffer = export_excel(tableaux, self.jour.year)
        wb = load_workbook(BytesIO(buffer.getvalue()))
        valeurs = [
            str(cellule.value).upper()
            for feuille in wb.worksheets
            for ligne in feuille.iter_rows()
            for cellule in ligne
            if cellule.value not in (None, '')
        ]
        self.assertFalse(
            [v for v in valeurs if 'CPFAE' in v],
            'un sigle CPFAE subsiste dans le classeur exporté',
        )
        self.assertTrue(
            any('INJS' in v for v in valeurs),
            'le classeur exporté ne porte aucune mention INJS',
        )

    def test_pdf_point_journalier_porte_le_nom_officiel(self):
        tableaux = self._tableaux()
        self.assertTrue(tableaux, 'fixture sans tableau : test non concluant')
        buffer = export_pdf(tableaux, self.jour.year)
        contenu = buffer.getvalue() if hasattr(buffer, 'getvalue') else bytes(buffer)
        texte = texte_pdf(contenu)
        self.assertNotIn(b'CPFAE', texte)
        self.assertTrue(
            b'Institut National de la Jeunesse' in texte or b'INJS' in texte,
            "l'en-tête INJS est absent du PDF exporté",
        )
