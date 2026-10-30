"""GET-INJS — import d'un fichier externe d'inscrits (situation n°2).

Scénario du commanditaire : l'établissement reçoit un fichier listant les
étudiants inscrits pour une année académique, produit **hors** de la chaîne de
parcours de l'application. Le GET-INJS doit savoir l'intégrer et générer les
emplois du temps des cohortes correspondantes.

Ces tests construisent leurs propres données (``TestCase`` : transaction
annulée en fin de test) ; la base de développement n'est jamais touchée.

Ce qui est vérifié ici :

1. la lecture tolérante des fichiers (CSV « ; », CSV « , », Excel) et des
   en-têtes réels (accents, casse, synonymes) ;
2. le rejet **motivé** ligne par ligne, jamais silencieux ;
3. la création des cohortes (groupe, vague) et le dénonmbrement réel ;
4. l'idempotence (réimporter ne duplique rien) et l'absence d'écriture en
   analyse ;
5. l'exclusion des formations hors périmètre INJS ;
6. le refus explicite quand une colonne obligatoire manque.
"""

import io

from django.test import TestCase

from edts.moteur import import_inscrits as I
from edts.models import InscriptionImportee
from edts.tests.test_lot2_moteur import FabriqueLMD
from scolarite.models import Groupe

CSV_ENTETE = 'matricule;nom;prenoms;sexe;formation;niveau;semestre;groupe;vague\n'


def _csv(lignes):
    return (CSV_ENTETE + '\n'.join(lignes) + '\n').encode('utf-8')


class BaseImportTest(TestCase):
    def setUp(self):
        self.f = FabriqueLMD(self).creer_base(perimetre='INJS', filiere='F01')
        self.formation = self.f.cycle
        self.annee = self.f.annee

    def importer(self, contenu, nom='inscrits.csv', appliquer=False):
        return I.importer_inscrits(
            annee_academique_id=self.annee.pk,
            nom_fichier=nom,
            contenu=contenu,
            appliquer=appliquer,
        )


class LectureDuFichierTests(BaseImportTest):
    def test_csv_point_virgule(self):
        rapport = self.importer(_csv([
            f'INJS-001;Kouassi;Aya;F;{self.formation.intitule};L1;S1;L1-G1;V1',
        ]))
        self.assertEqual(rapport.lignes_lues, 1)
        self.assertEqual(rapport.lignes_valides, 1)
        self.assertEqual(rapport.lignes_rejetees, 0)

    def test_csv_virgule(self):
        contenu = (
            'Matricule,Nom,Prenoms,Formation,Niveau,Groupe\n'
            f'INJS-002,Traoré,Ismaël,{self.formation.intitule},L1,L1-G1\n'
        ).encode('utf-8')
        rapport = self.importer(contenu)
        self.assertEqual(rapport.lignes_valides, 1)

    def test_entetes_reels_accentues_et_synonymes(self):
        """Un fichier métier n'a jamais l'en-tête exact attendu."""
        contenu = (
            'N° Matricule;NOM ET PRÉNOMS;Prénom(s);FILIÈRE;Niveau d’étude;'
            'Semestre;Groupe pédagogique;Vague\n'
            f'INJS-003;Yao;Séverin;{self.formation.intitule};L1;S1;L1-G2;V2\n'
        ).replace('NOM ET PRÉNOMS', 'Nom de famille').encode('utf-8')
        rapport = self.importer(contenu)
        self.assertEqual(rapport.lignes_valides, 1)
        self.assertIn('matricule', rapport.colonnes_reconnues)
        self.assertIn('prenoms', rapport.colonnes_reconnues)

    def test_xlsx(self):
        from openpyxl import Workbook

        classeur = Workbook()
        feuille = classeur.active
        feuille.append(['matricule', 'nom', 'prenoms', 'formation', 'niveau', 'groupe'])
        feuille.append(['INJS-004', 'Diallo', 'Aminata', self.formation.intitule, 'L1', 'L1-G3'])
        flux = io.BytesIO()
        classeur.save(flux)
        rapport = self.importer(flux.getvalue(), nom='inscrits.xlsx')
        self.assertIsNone(rapport.motif_echec)
        self.assertEqual(rapport.lignes_valides, 1)

    def test_format_non_supporte(self):
        rapport = self.importer(b'\x00\x01', nom='inscrits.pdf')
        self.assertEqual(rapport.motif_echec, I.REJET_FORMAT_NON_SUPPORTE)

    def test_fichier_vide(self):
        rapport = self.importer(b'', nom='vide.csv')
        self.assertEqual(rapport.motif_echec, I.REJET_FICHIER_VIDE)

    def test_colonnes_obligatoires_absentes(self):
        rapport = self.importer(b'nom;prenoms\nKouassi;Aya\n')
        self.assertEqual(rapport.motif_echec, I.REJET_COLONNES_ABSENTES)
        self.assertIn('matricule', rapport.detail['colonnes_manquantes'])

    def test_sexe_et_date_normalises(self):
        contenu = (
            'matricule;nom;formation;niveau;sexe;date_naissance\n'
            f'INJS-005;Kone;{self.formation.intitule};L1;Féminin;15/03/2004\n'
        ).encode('utf-8')
        rapport = self.importer(contenu, appliquer=True)
        self.assertEqual(rapport.creees, 1)
        ligne = InscriptionImportee.objects.get(matricule='INJS-005')
        self.assertEqual(ligne.sexe, 'F')
        self.assertEqual(str(ligne.date_naissance), '2004-03-15')


class RejetsMotivesTests(BaseImportTest):
    def test_matricule_manquant(self):
        rapport = self.importer(_csv([
            f';Kouassi;Aya;F;{self.formation.intitule};L1;S1;L1-G1;V1',
        ]))
        self.assertEqual(rapport.lignes_rejetees, 1)
        self.assertEqual(rapport.erreurs[0].motif, I.REJET_MATRICULE_MANQUANT)
        self.assertEqual(rapport.erreurs[0].ligne, 2)

    def test_formation_inconnue(self):
        rapport = self.importer(_csv([
            'INJS-006;X;Y;F;FORMATION QUI N EXISTE PAS;L1;S1;L1-G1;V1',
        ]))
        self.assertEqual(rapport.erreurs[0].motif, I.REJET_FORMATION_ABSENTE)

    def test_formation_hors_perimetre_injs(self):
        """Un cycle legacy n'est jamais recyclé en formation INJS."""
        legacy = FabriqueLMD(self).creer_base(perimetre='LEGACY', filiere='', suffixe='-L')
        rapport = self.importer(_csv([
            f'INJS-007;X;Y;F;{legacy.cycle.intitule};L1;S1;L1-G1;V1',
        ]))
        self.assertEqual(rapport.erreurs[0].motif, I.REJET_FORMATION_HORS_PERIMETRE)

    def test_semestre_incoherent_avec_le_niveau(self):
        rapport = self.importer(_csv([
            f'INJS-008;X;Y;F;{self.formation.intitule};L1;S5;L1-G1;V1',
        ]))
        self.assertEqual(rapport.erreurs[0].motif, I.REJET_SEMESTRE_ABSENT)

    def test_rapport_compte_les_lignes_reelles(self):
        rapport = self.importer(_csv([
            f'INJS-009;Bon;A;F;{self.formation.intitule};L1;S1;L1-G1;V1',
            ';Sans;Matricule;F;X;L1;S1;G;V',
            f'INJS-010;Mauvais;Niveau;F;{self.formation.intitule};L9;S1;L1-G1;V1',
        ]))
        self.assertEqual(rapport.lignes_lues, 3)
        self.assertEqual(rapport.lignes_valides, 1)
        self.assertEqual(rapport.lignes_rejetees, 2)


class EcritureEtIdempotenceTests(BaseImportTest):
    def test_analyse_necrit_rien(self):
        rapport = self.importer(_csv([
            f'INJS-011;Kouassi;Aya;F;{self.formation.intitule};L1;S1;L1-G1;V1',
        ]), appliquer=False)
        self.assertEqual(rapport.lignes_valides, 1)
        self.assertEqual(rapport.creees, 0)
        self.assertEqual(InscriptionImportee.objects.count(), 0)
        self.assertFalse(Groupe.objects.filter(nom='L1-G1').exists())

    def test_import_cree_inscriptions_et_cohortes(self):
        rapport = self.importer(_csv([
            f'INJS-012;Kouassi;Aya;F;{self.formation.intitule};L1;S1;L1-G1;V1',
            f'INJS-013;Traoré;Ismaël;M;{self.formation.intitule};L1;S1;L1-G1;V1',
        ]), appliquer=True)
        self.assertEqual(rapport.creees, 2)
        self.assertEqual(rapport.effectif_total, 2)
        self.assertEqual(rapport.cohortes[0]['effectif'], 2)

        groupe = Groupe.objects.get(nom='L1-G1')
        self.assertEqual(groupe.annee_academique_id, self.annee.pk)
        self.assertEqual(groupe.ref_formation_id, self.formation.pk)
        self.assertEqual(InscriptionImportee.objects.filter(groupe=groupe).count(), 2)

    def test_reimport_idempotent(self):
        contenu = _csv([
            f'INJS-014;Kouassi;Aya;F;{self.formation.intitule};L1;S1;L1-G1;V1',
        ])
        premier = self.importer(contenu, appliquer=True)
        second = self.importer(contenu, appliquer=True)
        self.assertEqual(premier.creees, 1)
        self.assertEqual(second.creees, 0)
        self.assertEqual(second.mises_a_jour, 1)
        self.assertEqual(InscriptionImportee.objects.count(), 1)

    def test_reimport_met_a_jour_la_cohorte(self):
        self.importer(_csv([
            f'INJS-015;Kouassi;Aya;F;{self.formation.intitule};L1;S1;L1-G1;V1',
        ]), appliquer=True)
        self.importer(_csv([
            f'INJS-015;Kouassi;Aya;F;{self.formation.intitule};L1;S1;L1-G2;V1',
        ]), appliquer=True)
        ligne = InscriptionImportee.objects.get(matricule='INJS-015')
        self.assertEqual(ligne.groupe.nom, 'L1-G2')
        self.assertEqual(InscriptionImportee.objects.count(), 1)

    def test_aucune_ligne_valide_n_laisse_rien(self):
        """Un fichier sans ligne exploitable ne crée pas de cohorte fantôme."""
        rapport = self.importer(_csv([
            f';Sans;Matricule;F;{self.formation.intitule};L1;S1;L1-G9;V1',
        ]), appliquer=True)
        self.assertEqual(rapport.lignes_valides, 0)
        self.assertEqual(rapport.creees, 0)
        self.assertEqual(InscriptionImportee.objects.count(), 0)
        self.assertFalse(Groupe.objects.filter(nom='L1-G9').exists())

    def test_empreinte_identifie_le_lot(self):
        contenu = _csv([
            f'INJS-016;Kouassi;Aya;F;{self.formation.intitule};L1;S1;L1-G1;V1',
        ])
        rapport = self.importer(contenu, appliquer=True)
        self.assertEqual(len(rapport.empreinte), 64)
        self.assertEqual(
            InscriptionImportee.objects.get(matricule='INJS-016').empreinte,
            rapport.empreinte,
        )


class EffectifsTests(BaseImportTest):
    def test_effectifs_par_groupe_ignorant_les_radies(self):
        self.importer(_csv([
            f'INJS-020;A;A;F;{self.formation.intitule};L1;S1;L1-G1;V1',
            f'INJS-021;B;B;M;{self.formation.intitule};L1;S1;L1-G1;V1',
        ]), appliquer=True)
        groupe = Groupe.objects.get(nom='L1-G1')
        InscriptionImportee.objects.filter(matricule='INJS-021').update(statut='RADIE')

        effectifs = I.effectifs_par_groupe(self.annee.pk)
        self.assertEqual(effectifs[groupe.pk], 1)

    def test_effectif_total_est_un_denombrement(self):
        lignes = [
            f'INJS-{100 + i:03d};Nom{i};Prenom;F;{self.formation.intitule};L1;S1;L1-G1;V1'
            for i in range(25)
        ]
        rapport = self.importer(_csv(lignes), appliquer=True)
        self.assertEqual(rapport.effectif_total, 25)
        self.assertEqual(InscriptionImportee.objects.count(), 25)
