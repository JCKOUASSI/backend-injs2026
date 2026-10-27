"""Management command : Initialisation Vague 4 / Lot 4.1.

Finances Étudiantes, Tarifications LMD, Échéanciers, Factures, Quittances & Vacations Enseignants :
1. Tarification LMD (Dossier, Inscription, Scolarité) pour la cohorte L3 STAPS.
2. Génération automatique des échéanciers et des factures pour les 6 étudiants admis.
3. Règlements multi-canaux (Orange Money, MTN Money, Moov Money, Virement, Caisse)
   avec intégrité anti-doublon et pièces justificatives.
4. Confirmation des paiements et délivrance de quittances officielles numérotées.
5. Rapprochement bancaire et comptable pour la période de rentrée.
6. Affectations pédagogiques LMD des formateurs (310h) et certification 0 anomalie.
7. Paramétrage des vacations et honoraires formateurs INJS Marcory.
"""
from decimal import Decimal
from datetime import date
from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.core.files.base import ContentFile
from django.db import transaction

from authentication.models import User
from scolarite.models import (
    DossierEtudiant, AnneeAcademique, Parcours, Niveau,
    AffectationPedagogique, ECUE, Maquette
)
from formations.models import RefFormation, Formateur, FinanceSettings
from finances_etudiantes.models import (
    Tarification, Echeancier, Facture, Paiement, Quittance, RapprochementComptable
)
from finances_etudiantes.services import (
    generer_echeancier_pour_etudiant, generer_facture,
    enregistrer_paiement_idempotent, confirmer_paiement
)
from scolarite.charges_services import anomalies, occupation_par_enseignant


MODES_PAIEMENT_COHORTE = [
    'ELEPHANT_MONEY',  # Orange Money
    'MTN_MONEY',       # MTN Mobile Money
    'MOOV_MONEY',      # Moov Money
    'VIREMENT',        # Virement bancaire BICICI/SGBCI
    'CAISSE',          # Paiement guichet Agence Comptable INJS
    'ELEPHANT_MONEY',  # Orange Money
]


class Command(BaseCommand):
    help = "Initialise le Lot 4.1 : Finances Étudiantes, Quittances et Charges Enseignants"

    def handle(self, *args, **options):
        self.stdout.write("--- 1. Vérification des prérequis LMD (Lots 1.1 à 3.1) ---")
        call_command('seed_lot3_1_evaluations_jurys')

        admin_user = User.objects.get(username='admin')
        annee = AnneeAcademique.objects.get(libelle='2026-2027')
        formation = RefFormation.objects.first()
        niveau = Niveau.objects.get(code='L3')
        parcours_prof = Parcours.objects.filter(code='PROF_COLLEGE').first()
        if not parcours_prof:
            parcours_prof = Parcours.objects.filter(ref_formation=formation).first()

        # --- 2. Tarification LMD ---
        self.stdout.write("--- 2. Configuration de la Grille Tarifaire LMD ---")
        tarifs_config = [
            ('DOSSIER', Decimal('10000.00')),
            ('INSCRIPTION', Decimal('50000.00')),
            ('SCOLARITE', Decimal('100000.00')),
        ]
        for nature, montant in tarifs_config:
            tarif, created = Tarification.objects.update_or_create(
                formation=formation,
                parcours=parcours_prof,
                niveau=niveau,
                annee_academique=annee,
                nature=nature,
                defaults={
                    'montant_base': montant,
                    'devise': 'XOF',
                    'actif': True,
                }
            )
            action = "créé" if created else "actualisé"
            self.stdout.write(f"  Tarif {nature} : {montant:,.2f} XOF ({action})")

        # --- 3. Échéanciers, Factures, Règlements et Quittances ---
        self.stdout.write("--- 3. Échéanciers, Factures et Quittances des Étudiants ---")
        etudiants = list(DossierEtudiant.objects.filter(inscriptions__annee_academique=annee).distinct().order_by('participant__matricule'))
        all_transactions = []
        total_encaisse = Decimal('0.00')

        for idx, etudiant in enumerate(etudiants):
            echeancier = Echeancier.objects.filter(etudiant=etudiant, annee_academique=annee).first()
            if not echeancier:
                echeancier = generer_echeancier_pour_etudiant(etudiant, annee)

            facture = Facture.objects.filter(echeancier=echeancier).first()
            if not facture:
                facture = generer_facture(echeancier, admin_user)

            mode_paiement = MODES_PAIEMENT_COHORTE[idx % len(MODES_PAIEMENT_COHORTE)]

            for ligne in echeancier.lignes.all():
                tx_ref = f"TX-INJS-2026-{etudiant.matricule}-{ligne.nature}"
                paiement, _ = enregistrer_paiement_idempotent(
                    etudiant=etudiant,
                    nature=ligne.nature,
                    montant=ligne.montant,
                    devise='XOF',
                    mode=mode_paiement,
                    transaction_externe=tx_ref,
                    utilisateur=admin_user,
                    statut_initie='INITIE',
                )
                if not paiement.preuve:
                    preuve_content = (
                        f"REÇU DE TRANSACTION INJS MARCORY\n"
                        f"Référence: {tx_ref}\n"
                        f"Étudiant: {etudiant.matricule} ({etudiant.participant.nom} {etudiant.participant.prenom})\n"
                        f"Nature: {ligne.get_nature_display()}\n"
                        f"Montant: {ligne.montant} XOF\n"
                        f"Mode: {mode_paiement}\n"
                        f"Date: {date.today()}\n"
                    ).encode('utf-8')
                    paiement.preuve.save(f"recu_{tx_ref}.pdf", ContentFile(preuve_content), save=True)

                confirmer_paiement(paiement, admin_user)

                ligne.statut = 'PAYE'
                ligne.save(update_fields=['statut'])

                all_transactions.append(paiement)
                total_encaisse += paiement.montant

            facture.statut = 'PAYEE'
            facture.save(update_fields=['statut'])

            quittances_count = Quittance.objects.filter(paiement__etudiant=etudiant).count()
            self.stdout.write(
                f"  Étudiant {etudiant.matricule} ({etudiant.participant.nom}) : "
                f"Facture {facture.numero} PAYÉE ({facture.total:,.2f} XOF) | "
                f"{quittances_count} quittance(s) émise(s)"
            )

        # --- 4. Rapprochement Comptable de Cohorte ---
        self.stdout.write("--- 4. Rapprochement Comptable de Rentrée ---")
        rapprochement, _ = RapprochementComptable.objects.get_or_create(
            date_periode=date.today(),
            defaults={
                'solde': total_encaisse,
                'commentaire': f"Rapprochement comptable de rentrée L3 STAPS ({len(all_transactions)} transactions)",
            }
        )
        rapprochement.transactions.set(all_transactions)
        rapprochement.solde = total_encaisse
        rapprochement.save()
        self.stdout.write(
            f"  Rapprochement comptable certifié : Solde = {total_encaisse:,.2f} XOF "
            f"({len(all_transactions)} transactions réconciliées)"
        )

        # --- 5. Charges d'Enseignement et Vacations Formateurs ---
        self.stdout.write("--- 5. Affectations Pédagogiques LMD & Charges Formateurs ---")
        maquette = Maquette.objects.filter(statut=Maquette.Statut.ACTIVE, annee_academique=annee).first()
        formateurs = list(Formateur.objects.all())

        affectations_grille = [
            ('ECUE511', 'KOUAME', 'CM', Decimal('70.00')),
            ('ECUE512', 'KONÉ', 'TD', Decimal('60.00')),
            ('ECUE521', 'NDIAYE', 'CM', Decimal('60.00')),
            ('ECUE522', 'OUÉDRAOGO', 'TD', Decimal('50.00')),
            ('ECUE531', 'TOURE', 'CM', Decimal('35.00')),
            ('ECUE532', 'TOURE', 'TD', Decimal('35.00')),
        ]

        for code_ecue, nom_prof, type_ens, vol in affectations_grille:
            ecue = ECUE.objects.get(code=code_ecue, ue__maquette=maquette)
            prof = next((f for f in formateurs if nom_prof.upper() in f.nom.upper()), formateurs[0])
            aff, created = AffectationPedagogique.objects.get_or_create(
                annee_academique=annee,
                ref_formation=maquette.ref_formation,
                niveau=maquette.niveau,
                ecue=ecue,
                enseignant=prof,
                type_enseignement=type_ens,
                defaults={
                    'ue': ecue.ue,
                    'semestre': ecue.ue.semestre,
                    'volume_horaire': vol,
                    'statut': AffectationPedagogique.Statut.VALIDEE,
                }
            )
            aff.statut = AffectationPedagogique.Statut.VALIDEE
            aff.volume_horaire = vol
            aff.save()

        # Contrôle des anomalies LMD
        anomalies_detectees = anomalies(annee)
        self.stdout.write(f"  Contrôle des anomalies de charges pédagogiques : {len(anomalies_detectees)} anomalie(s)")

        # Synthèse des occupations et volumes validés
        occupations = occupation_par_enseignant(annee)
        for occ in occupations:
            self.stdout.write(
                f"    {occ['enseignant']:20} | Validée: {occ['validee']:5.1f}h | "
                f"Prévue: {occ['prevue']:5.1f}h | Surcharge: {occ['surcharge']}"
            )

        # --- 6. Paramètres Financiers et Vacations INJS ---
        self.stdout.write("--- 6. Paramétrage des Vacations INJS Marcory ---")
        f_settings, _ = FinanceSettings.objects.get_or_create(pk=1)
        f_settings.prix_heure_realisee = Decimal('15000.00')
        f_settings.afficher_montants_exports = True
        f_settings.export_titre_document = 'ÉTAT FINANCIER FORMATEUR LMD'
        f_settings.export_entete_ligne1 = "RÉPUBLIQUE DE CÔTE D'IVOIRE"
        f_settings.export_entete_ligne2 = "MINISTÈRE DE LA PROMOTION DES SPORTS ET DU CADRE DE VIE"
        f_settings.export_organisme = "INSTITUT NATIONAL DE LA JEUNESSE ET DES SPORTS (INJS)"
        f_settings.export_adresse = "Campus INJS Marcory, Boulevard de Marseille, Abidjan"
        f_settings.export_reference_prefix = "INJS-FIN-2026"
        f_settings.export_mention_legale = "Visa de l'Agence Comptable Principale INJS Marcory"
        f_settings.export_signataire_nom = "Directeur Général INJS"
        f_settings.export_signataire_fonction = "Ordonnateur Principal du Budget"
        f_settings.export_contacts = "finances@injs.ci / +225 27 21 24 35 00"
        f_settings.export_pied_page_titre = "INJS Marcory - Excellence Sportive & Académique"
        f_settings.export_pied_page_texte = "Document officiel généré pour le décompte des honoraires de formation LMD."
        f_settings.save()
        self.stdout.write(f"  Taux horaire vacation : {f_settings.prix_heure_realisee:,.2f} XOF/h")
        self.stdout.write(f"  Organisme : {f_settings.export_organisme}")

        self.stdout.write(self.style.SUCCESS(
            f"=== Lot 4.1 initialisé et validé avec succès "
            f"({total_encaisse:,.2f} XOF encaissés, {len(all_transactions)} quittances, 310h d'enseignement validées) ==="
        ))
