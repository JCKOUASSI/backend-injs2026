"""Management command : Initialisation Vague 5 / Lot 5.1.

Domaines Transversaux :
1. Conventions de Stages Professionnels LMD (Organismes, tuteurs, workflow et évaluations).
2. Administration & GED (Directions, Départements, Courriers tracés, Documents officiels versionnés).
3. Ressources Humaines (Services, Fonctions, Agents, Affectations RH et Disponibilités).
4. Patrimoine & Installations Sportives INJS Marcory (Équipements de pointe, Véhicules, Inventaire,
   Maintenances et Réservations d'espaces sportifs).
"""
from datetime import date, timedelta
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.utils import timezone

from authentication.models import User
from scolarite.models import DossierEtudiant, AnneeAcademique
from formations.models import RefFormation, RefSalle, Formateur

# 1. Stages
from stages.models import OrganismeAccueil, TuteurExterne, ConventionStage, EvaluationStage
from stages.services import (
    appliquer_transition, enregistrer_evaluation,
)

# 2. Administrations
from administrations.models import (
    Direction, Departement, Courrier, DocumentOfficiel, VersionDocument
)
from administrations.services import (
    creer_version_document, valider_document,
)

# 3. Ressources Humaines
from ressources_humaines.models import (
    Service, Fonction, Agent, AffectationRH, DisponibiliteAgent
)

# 4. Patrimoine
from patrimoine.models import (
    Equipement, Vehicule, Inventaire, LigneInventaire, Maintenance, ReservationEspace
)


class Command(BaseCommand):
    help = "Initialise le Lot 5.1 : Stages, Administration/GED, RH et Patrimoine INJS Marcory"

    def handle(self, *args, **options):
        self.stdout.write("--- 1. Vérification des prérequis LMD (Lots 1.1 à 4.1) ---")
        call_command('seed_lot4_1_finances')

        admin_user = User.objects.get(username='admin')
        annee = AnneeAcademique.objects.get(libelle='2026-2027')
        formation = RefFormation.objects.first()
        etudiants = list(DossierEtudiant.objects.filter(inscriptions__annee_academique=annee).distinct().order_by('participant__matricule'))
        formateurs = list(Formateur.objects.filter(user__isnull=False))
        formateur_user = formateurs[0].user if formateurs else admin_user

        # =========================================================================
        # 2. STAGES PROFESSIONNELS LMD
        # =========================================================================
        self.stdout.write("--- 2. Conventions de Stages Professionnels LMD ---")
        organismes_data = [
            ("Fédération Ivoirienne d'Athlétisme (FIA)", "Stade Félix Houphouët-Boigny, Plateau, Abidjan", "BAMBA Lanciné", "dtn@fia.ci", "+225 07070701"),
            ("Office National des Sports (ONS - CI)", "Boulevard lagunaire, Treichville, Abidjan", "KOUADIO Roger", "infrastructures@ons.ci", "+225 07080802"),
            ("Centre Médico-Sportif d'Excellence INJS", "Campus INJS Marcory, Boulevard de Marseille", "Dr ASSI Marie", "cms@injs.ci", "+225 07090903"),
            ("Sotra Sports & Loisirs", "Dépôt Sotra Vridi, Zone Industrielle", "TRAORE Bakary", "sports@sotra.ci", "+225 07101004"),
        ]
        org_objs = []
        for nom, adr, c_nom, c_email, c_tel in organismes_data:
            org, _ = OrganismeAccueil.objects.update_or_create(
                nom=nom,
                defaults={
                    'adresse': adr,
                    'contact_nom': c_nom,
                    'contact_email': c_email,
                    'contact_telephone': c_tel,
                    'ville': 'Abidjan',
                    'actif': True,
                }
            )
            tut, _ = TuteurExterne.objects.update_or_create(
                organisme=org, nom=c_nom.split()[0], prenom=' '.join(c_nom.split()[1:]),
                defaults={
                    'email': c_email,
                    'telephone': c_tel,
                    'fonction': 'Tuteur de Stage Professionnel',
                    'actif': True,
                }
            )
            org_objs.append((org, tut))

        stages_sujets = [
            ("Optimisation de la foulée et planification de l'entraînement sprint cadets", Decimal('18.00'), Decimal('17.50'), Decimal('18.00'), Decimal('17.00'), Decimal('18.00')),
            ("Développement des qualités aérobies et réathlétisation des footballeurs U20", Decimal('17.00'), Decimal('16.50'), Decimal('17.00'), Decimal('16.00'), Decimal('17.00')),
            ("Protocole d'évaluation de la puissance musculaire par analyse vidéo biomécanique", Decimal('16.00'), Decimal('16.00'), Decimal('16.50'), Decimal('15.50'), Decimal('16.00')),
            ("Conception et animation de cycles d'athlétisme en collège : pédagogie inclusive", Decimal('17.50'), Decimal('18.00'), Decimal('17.50'), Decimal('17.00'), Decimal('17.50')),
            ("Gestion de l'échauffement dynamique et prévention des blessures musculaires", Decimal('15.50'), Decimal('16.00'), Decimal('15.50'), Decimal('15.00'), Decimal('15.50')),
            ("Management d'un centre d'entraînement et encadrement des jeunes talents sportifs", Decimal('18.00'), Decimal('18.00'), Decimal('18.00'), Decimal('17.50'), Decimal('18.00')),
        ]

        for idx, etu in enumerate(etudiants):
            org, tut = org_objs[idx % len(org_objs)]
            sujet_info = stages_sujets[idx % len(stages_sujets)]
            encadrant = formateurs[idx % len(formateurs)].user if formateurs else admin_user

            conv, _ = ConventionStage.objects.update_or_create(
                etudiant=etu,
                annee_academique=annee,
                defaults={
                    'organisme': org,
                    'tuteur_externe': tut,
                    'encadrant_interne': encadrant,
                    'ref_formation': formation,
                    'intitule': f"Stage Professionnel L3 STAPS – {etu.participant.nom}",
                    'sujet': sujet_info[0],
                    'objectifs': "Mise en application des compétences pédagogiques et biomécaniques acquises à l'INJS.",
                    'date_debut': date(2026, 10, 1),
                    'date_fin': date(2026, 12, 31),
                    'lieu': org.nom,
                    'cree_par': admin_user,
                }
            )

            # Workflow complet jusqu'à SOUTENUE
            transitions = [
                ConventionStage.Statut.SOUMISE,
                ConventionStage.Statut.VALIDEE,
                ConventionStage.Statut.SIGNEE,
                ConventionStage.Statut.EN_COURS,
                ConventionStage.Statut.TERMINEE,
                ConventionStage.Statut.SOUTENUE,
            ]
            for st in transitions:
                if conv.statut != st and conv.statut != ConventionStage.Statut.VALIDEE_JURY:
                    try:
                        conv = appliquer_transition(conv, st.value, admin_user)
                    except Exception:
                        pass

            # Clôture par évaluation validée du jury
            if conv.statut == ConventionStage.Statut.SOUTENUE:
                enregistrer_evaluation(
                    conv,
                    note_aptitude=sujet_info[1],
                    note_integration=sujet_info[2],
                    note_autonomie=sujet_info[3],
                    note_production=sujet_info[4],
                    note_rapport=sujet_info[5],
                    appreciation_libre=f"Stagiaire remarquable ({etu.matricule}) ayant fait honneur à la formation INJS.",
                    user=admin_user,
                    valider=True,
                )
                conv.refresh_from_db()

            self.stdout.write(
                f"  Convention {conv.id} ({etu.matricule}) : {org.nom} | "
                f"Statut : {conv.statut} | Note soutenance : {conv.note_soutenance} | Mention : {conv.mention}"
            )

        # =========================================================================
        # 3. ADMINISTRATION GÉNÉRALE ET GED INSTITUTIONNELLE
        # =========================================================================
        self.stdout.write("--- 3. Administration Générale et GED Institutionnelle ---")
        # Directions
        dir_dg, _ = Direction.objects.update_or_create(
            code='DIR-GEN',
            defaults={
                'libelle': "Direction Générale de l'INJS",
                'description': "Pilotage stratégique, gouvernance institutionnelle et relations ministérielles.",
                'responsable': admin_user,
                'telephone': "+225 27 21 24 35 01",
                'email': "dg@injs.ci",
                'localisation': "Bâtiment Administratif Central, 2ème étage",
                'ordre': 1,
                'actif': True,
            }
        )
        dir_sg, _ = Direction.objects.update_or_create(
            code='SEC-GEN',
            defaults={
                'libelle': "Secrétariat Général de l'INJS",
                'description': "Coordination des services administratifs, financiers et du patrimoine.",
                'responsable': admin_user,
                'telephone': "+225 27 21 24 35 02",
                'email': "sg@injs.ci",
                'localisation': "Bâtiment Administratif Central, 1er étage",
                'ordre': 2,
                'actif': True,
            }
        )
        dir_etudes, _ = Direction.objects.update_or_create(
            code='DIR-ETUDES',
            defaults={
                'libelle': "Direction des Études et des Stages (DES)",
                'description': "Pilotage pédagogique des maquettes LMD, des examens et de la scolarité.",
                'responsable': formateur_user,
                'telephone': "+225 27 21 24 35 03",
                'email': "etudes@injs.ci",
                'localisation': "Bâtiment Pédagogique A, R+1",
                'ordre': 3,
                'actif': True,
            }
        )

        # Départements
        dep_staps, _ = Departement.objects.update_or_create(
            code='DEP-STAPS',
            defaults={
                'libelle': "Département des Sciences et Techniques des Activités Physiques et Sportives (STAPS)",
                'description': "Filières Licence et Master STAPS, entraînement sportif et éducation physique.",
                'direction': dir_etudes,
                'responsable': formateur_user,
                'localisation': "Bâtiment STAPS, Rez-de-chaussée",
                'ordre': 1,
                'actif': True,
            }
        )
        dep_jepl, _ = Departement.objects.update_or_create(
            code='DEP-JEPL',
            defaults={
                'libelle': "Département de la Jeunesse, de l'Éducation Populaire et des Loisirs",
                'description': "Filières d'animation socio-éducative et gestion des loisirs sportifs.",
                'direction': dir_etudes,
                'localisation': "Bâtiment JEPL, R+1",
                'ordre': 2,
                'actif': True,
            }
        )

        # Courriers
        Courrier.objects.update_or_create(
            reference='CR-ENT-2026-0012',
            defaults={
                'sens': Courrier.Sens.ENTRANT,
                'objet': "Homologation ministérielle de la Maquette L3 Professorat STAPS 2026-2027",
                'expediteur': "Ministère de la Promotion des Sports et du Cadre de Vie",
                'destinataire': "Direction Générale de l'INJS",
                'date_courrier': date(2026, 9, 1),
                'statut': Courrier.Statut.CLASSE,
                'cree_par': admin_user,
            }
        )
        Courrier.objects.update_or_create(
            reference='CR-SORT-2026-0008',
            defaults={
                'sens': Courrier.Sens.SORTANT,
                'objet': "Transmission du Procès-Verbal officiel de délibération de la session de Jury L3 STAPS",
                'expediteur': "Direction des Études et des Stages INJS",
                'destinataire': "Direction Générale de l'Enseignement Supérieur (DGES)",
                'date_courrier': date(2026, 9, 15),
                'statut': Courrier.Statut.REPONDU,
                'cree_par': admin_user,
            }
        )

        # Documents Officiels & Versions
        doc_ns, _ = DocumentOfficiel.objects.update_or_create(
            reference='NS-2026-042',
            defaults={
                'type_document': DocumentOfficiel.Type.NOTE_SERVICE,
                'titre': "Calendrier officiel de rentrée académique et des examens LMD 2026-2027",
                'contenu': (
                    "La Direction Générale de l'INJS informe l'ensemble de la communauté universitaire que "
                    "les enseignements du Semestre 5 débutent officiellement le 15 Septembre 2026 sur le Campus Marcory."
                ),
                'statut': DocumentOfficiel.Statut.PUBLIE,
                'signe_par': admin_user,
                'date_signature': timezone.now(),
                'cree_par': admin_user,
            }
        )
        creer_version_document(doc_ns, contenu=doc_ns.contenu, acteur=admin_user)

        doc_arr, _ = DocumentOfficiel.objects.update_or_create(
            reference='ARR-2026-088',
            defaults={
                'type_document': DocumentOfficiel.Type.ARRETE,
                'titre': "Arrêté portant proclamation des résultats et délivrance des diplômes L3 STAPS",
                'contenu': "Sont déclarés définitivement admis au grade de Licence STAPS les six candidats de la session normale 2026.",
                'statut': DocumentOfficiel.Statut.SIGNE,
                'signe_par': admin_user,
                'date_signature': timezone.now(),
                'cree_par': admin_user,
            }
        )
        creer_version_document(doc_arr, contenu=doc_arr.contenu, acteur=admin_user)
        self.stdout.write(f"  Organigramme : {Direction.objects.count()} directions, {Departement.objects.count()} départements")
        self.stdout.write(f"  GED : {Courrier.objects.count()} courriers tracés, {DocumentOfficiel.objects.count()} documents officiels publiés")

        # =========================================================================
        # 4. RESSOURCES HUMAINES
        # =========================================================================
        self.stdout.write("--- 4. Ressources Humaines & Agents INJS ---")
        serv_scol, _ = Service.objects.update_or_create(
            nom="Service de la Scolarité Centrale et du Suivi LMD",
            defaults={
                'code': 'SERV-SCOL',
                'type_unite': Service.TypeUnite.SERVICE,
                'departement': dep_staps,
                'description': "Gestion des inscriptions, des dossiers étudiants, des jurys et de la diplomation.",
                'responsable': admin_user,
                'localisation': "Bâtiment Administratif, RDC, Aile Ouest",
                'actif': True,
            }
        )
        serv_med, _ = Service.objects.update_or_create(
            nom="Service Médico-Sportif et Réathlétisation",
            defaults={
                'code': 'SERV-MED',
                'type_unite': Service.TypeUnite.SERVICE,
                'departement': dep_staps,
                'description': "Suivi médical d'aptitude sportive, traumatologie et réathlétisation.",
                'responsable': formateur_user,
                'localisation': "Centre Médico-Sportif INJS",
                'actif': True,
            }
        )
        serv_pat, _ = Service.objects.update_or_create(
            nom="Service des Équipements et Patrimoine Sportif",
            defaults={
                'code': 'SERV-PAT',
                'type_unite': Service.TypeUnite.SERVICE,
                'departement': dep_staps,
                'description': "Gestion et maintenance des installations sportives et laboratoires d'analyse.",
                'responsable': admin_user,
                'localisation': "Complexe Sportif, Entrée Principale",
                'actif': True,
            }
        )

        fct_scol, _ = Fonction.objects.update_or_create(
            intitule="Chef du Service Scolarité et Examens LMD",
            service=serv_scol,
            defaults={'grade': "Attaché Principal des Services Universitaires", 'actif': True}
        )
        fct_med, _ = Fonction.objects.update_or_create(
            intitule="Médecin du Sport / Responsable Suivi des Athlètes",
            service=serv_med,
            defaults={'grade': "Praticien Hospitalo-Universitaire", 'actif': True}
        )
        fct_pat, _ = Fonction.objects.update_or_create(
            intitule="Gestionnaire du Patrimoine et des Installations",
            service=serv_pat,
            defaults={'grade': "Ingénieur des Travaux Publics", 'actif': True}
        )

        agents_data = [
            ('AG-INJS-2026-001', 'KOUASSI', 'Jean-Claude', 'jc.kouassi@injs.ci', Agent.TypeContrat.FONCTIONNAIRE, fct_scol),
            ('AG-INJS-2026-002', 'DR ASSI', 'Marie-Paule', 'mp.assi@injs.ci', Agent.TypeContrat.CONTRAT, fct_med),
            ('AG-INJS-2026-003', 'YAO', 'Koffi Blaise', 'kb.yao@injs.ci', Agent.TypeContrat.FONCTIONNAIRE, fct_pat),
        ]
        for mat, nom, prenom, email, contrat, fct in agents_data:
            ag, _ = Agent.objects.update_or_create(
                matricule=mat,
                defaults={
                    'nom': nom,
                    'prenom': prenom,
                    'email': email,
                    'type_contrat': contrat,
                    'statut': Agent.Statut.ACTIF,
                    'date_entree': date(2021, 10, 1),
                }
            )
            AffectationRH.objects.update_or_create(
                agent=ag,
                fonction=fct,
                defaults={'date_debut': date(2026, 1, 1), 'cree_par': admin_user}
            )

        # Disponibilité planifiée (Mission d'encadrement sportive)
        ag_premier = Agent.objects.first()
        DisponibiliteAgent.objects.update_or_create(
            agent=ag_premier,
            date_debut=date(2026, 11, 10),
            date_fin=date(2026, 11, 15),
            defaults={
                'type_indispo': DisponibiliteAgent.TypeIndispo.MISSION,
                'motif': "Supervision technique des délégations INJS aux Jeux Universitaires Ouest-Africains",
            }
        )
        self.stdout.write(f"  RH : {Service.objects.count()} services, {Fonction.objects.count()} fonctions, {Agent.objects.count()} agents actifs affectés")

        # =========================================================================
        # 5. PATRIMOINE ET ESPACES SPORTIFS INJS MARCORY
        # =========================================================================
        self.stdout.write("--- 5. Patrimoine & Installations Sportives INJS Marcory ---")
        salles = list(RefSalle.objects.all())
        salle_piste = salles[0] if salles else None
        salle_labo = salles[1] if len(salles) > 1 else salle_piste

        equipements_data = [
            ("Système de chronométrage électronique 8 couloirs", Equipement.TypeEquipement.MATERIEL_SPORT, "Microgate", "Racetime2", "CHRONO-2026-01", salle_piste),
            ("Cellules photoélectriques sans fil et barres Optojump", Equipement.TypeEquipement.MATERIEL_SPORT, "Microgate", "Optojump Next", "OPTO-2026-02", salle_labo),
            ("Analyseur portatif de métabolisme et VO2Max", Equipement.TypeEquipement.MATERIEL_SPORT, "Cosmed", "K5", "COSMED-2026-03", salle_labo),
            ("Ergomètre à freinage électromagnétique d'effort", Equipement.TypeEquipement.MATERIEL_SPORT, "Monark", "LC7TT", "MONARK-2026-04", salle_labo),
            ("Tableau d'affichage électronique matriciel multisports", Equipement.TypeEquipement.MATERIEL_SPORT, "Bodet", "BTX6000", "BODET-2026-05", salle_piste),
        ]
        equip_objs = []
        for nom, t_eq, marque, modele, num_s, espace in equipements_data:
            eq, _ = Equipement.objects.update_or_create(
                num_serie=num_s,
                defaults={
                    'nom': nom,
                    'type_equipement': t_eq,
                    'marque': marque,
                    'modele': modele,
                    'espace': espace,
                    'etat': Equipement.Etat.FONCTIONNEL,
                    'date_acquisition': date(2024, 6, 1),
                    'cree_par': admin_user,
                }
            )
            equip_objs.append(eq)

        # Véhicules
        vehicules_data = [
            ("1234-HJ-01", "Toyota", "Coaster 30 places", 2024, 18500, "Minibus transport des sélections sportives INJS"),
            ("5678-KL-01", "Toyota", "Hilux Double Cabine 4x4", 2023, 34200, "Véhicule d'intervention et logistique pistes"),
            ("9012-MN-01", "Peugeot", "508 Allure", 2024, 9800, "Véhicule de liaison Direction Générale"),
        ]
        for immat, marq, mod, an, km, notes in vehicules_data:
            Vehicule.objects.update_or_create(
                immatriculation=immat,
                defaults={
                    'marque': marq,
                    'modele': mod,
                    'annee_mise_en_circulation': an,
                    'kilometrage': km,
                    'prochaine_revision': date(2027, 3, 1),
                    'notes': notes,
                }
            )

        # Campagne d'inventaire
        inv, _ = Inventaire.objects.update_or_create(
            date_inventaire=date.today(),
            defaults={
                'responsable': admin_user,
                'commentaires': "Campagne d'inventaire physique des matériels biomécaniques et sportifs – Rentrée 2026.",
            }
        )
        for eq in equip_objs:
            LigneInventaire.objects.update_or_create(
                inventaire=inv, equipement=eq,
                defaults={'etat_constate': Equipement.Etat.FONCTIONNEL, 'commentaires': "Matériel vérifié conforme et opérationnel."}
            )

        # Maintenance préventive réalisée
        if equip_objs:
            Maintenance.objects.update_or_create(
                equipement=equip_objs[0],
                date_debut=date(2026, 9, 1),
                defaults={
                    'type_maintenance': Maintenance.TypeMaintenance.PREVENTIVE,
                    'description': "Étalonnage annuel des capteurs de départ et récepteur optique d'arrivée.",
                    'date_fin': date(2026, 9, 3),
                    'statut': Maintenance.Statut.TERMINEE,
                    'responsable': admin_user,
                }
            )

        # Réservation d'espace pour la cohorte L3 STAPS
        if salle_piste:
            ReservationEspace.objects.update_or_create(
                salle=salle_piste,
                motif="Séance pratique d'athlétisme et évaluation biométrique L3 STAPS",
                defaults={
                    'date_debut': timezone.now() + timedelta(days=1, hours=8),
                    'date_fin': timezone.now() + timedelta(days=1, hours=11),
                    'statut': ReservationEspace.Statut.VALIDEE,
                    'demande_par': formateur_user,
                    'valide_par': admin_user,
                }
            )

        self.stdout.write(f"  Patrimoine : {Equipement.objects.count()} équipements de pointe, {Vehicule.objects.count()} véhicules, {Inventaire.objects.count()} inventaire(s)")
        self.stdout.write(f"  Maintenance & Espaces : {Maintenance.objects.count()} maintenance(s), {ReservationEspace.objects.count()} réservation(s) validée(s)")

        self.stdout.write(self.style.SUCCESS(
            "=== Lot 5.1 initialisé et validé avec succès (Conventions, GED, RH & Patrimoine opérationnels) ==="
        ))
