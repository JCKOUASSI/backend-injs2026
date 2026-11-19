"""Protocole Présences QR : DOCX/PDF synchronisés, aucun test exécuté."""
from pathlib import Path
from xml.sax.saxutils import escape
from docx import Document
from docx.shared import Cm, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from reportlab.platypus import SimpleDocTemplate, Paragraph, KeepTogether, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.pagesizes import A4

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'dossier_trvx/Manuel_jeu_PrésencesQR2026'
BASE='Manuel_Demo_Recette_Presences_QR_2026'
TITLE='MANUEL DÉMO DE RECETTE DE BOUT EN BOUT — PRÉSENCES QR'
CHAPTERS=[]
def chapter(name,intro):CHAPTERS.append({'name':name,'intro':intro,'cases':[]})
def case(title,steps,expected,source,profile='Compte habilité',evidence=None):
 n=sum(len(c['cases']) for c in CHAPTERS)+1
 CHAPTERS[-1]['cases'].append(dict(id=f'PQR-{n:03d}',title=title,steps=steps,expected=expected,source=source,profile=profile,evidence=evidence or 'Capture expurgée + ID de séance/pointage, réponse HTTP/code et horodatage, hors jeton et GPS brut.'))

chapter('1. Préparer la chaîne LMD et les droits','Préflight : inscription administrative validée et inscription pédagogique explicite si requise, groupe, EDT et affectation de créneau, enseignant/encadrant habilité, salle/site, puis séance du jour. Une séance récurrente est calculée à partir de la date de début de l’année et de la semaine; ne pas présumer que la génération annuelle est validée.')
case('Année, groupe et EDT publié','Dans une base de recette, préparer année, groupe, étudiant inscrit, enseignant, salle/site; publier un EDT autorisé et relever affectation ID.','La séance du jour est rattachée à une affectation active; comparer semaine et jour réels.','edts/models.py; seances_edt_services.py',profile='Planificateur / Direction')
case('EDT brouillon et séance annulée','Comparer /presences/seances et /seances-edt/du-jour/ avant publication, puis après annulation logique.','Brouillon non considéré comme séance du jour; séance annulée non badgeable.','seances_edt_services.py; seances_edt_api.py')
case('Semaines S1 et S2','Préparer deux séances sur semaines officiellement approuvées S1/S2; vérifier jours, semaine académique, année et groupe.','Aucun pointage ne doit être associé à une autre semaine ou semestre; calendrier absent = blocage.','seances_edt_services.py; edts/moteur/annee.py')
case('Étudiant non inscrit ou inscription non validée','Comparer étudiant du groupe réellement inscrit et dossier non validé; ouvrir liste attendue de la séance.','Seuls membres autorisés sont attendus; aucune affiliation déduite du nom.','seances_edt_services.py; participant_scope.py')
case('ECUE de séance et pointage','Avec une séance générée de la maquette UE/ECUE, badger un étudiant fictif puis comparer séance et Pointage.','Rattachement ECUE de la séance vers le pointage vérifiable; historique incomplet signalé, non reconstruit.','seances_edt_services.py; edts/models.py')
case('Droits web et CURP','Tester lecture, ouverture QR, émargement et clôture avec enseignant du créneau, secrétariat habilité puis non habilité.','Permissions serveur + garde sur séance appliquées; accès non autorisé refusé, aucun geste enregistré.','seances_edt_api.py; frontend/src/menu/arborescence.js')
case('Session expirée et changement de mot de passe','Déconnecter puis tenter scan; tester compte marqué must_change_password sur jeu isolé.','401/403 selon contexte; aucun pointage et consigne de changement du mot de passe.','seances_edt_api.py; views.py',profile='Sécurité / testeur')

chapter('2. Hub, séances et supervision','Les écrans /presences et /presences/seances consultent /api/presences/seances-edt/supervision/; ouverture, recherche et rafraîchissement sont sans effet de bord : pas de QR créé ni de clôture provoquée.')
case('Accueil du jour','Ouvrir /presences, choisir Aujourd’hui, comparer séances et compteurs à /supervision/?date=… sur jeu isolé.','Indicateurs viennent des données serveur; aucun taux inventé si dénominateur inconnu.','PresencesHub.jsx; seances_supervision.py')
case('Jour précédent et jour sans séance','Sélectionner Hier puis une date sans occurrence; comparer avec les affectations planifiées.','États vides explicites; aucun QR ou pointage ajouté en consultation.','PresencesHub.jsx; seances_edt_api.py')
case('Filtre service et anomalies','Filtrer les services et ouvrir les anomalies du hub; relever séances et compteurs avant/après.','Filtres cohérents; anomalie ne devient pas présence validée.','PresencesHub.jsx; seances_supervision.py')
case('Registre des séances par jour','Ouvrir /presences/seances; choisir date, statut et recherche; comparer les lignes serveur.','Séances de la date et statuts cohérents; détails ouvrent le bon registre.','SeancesRegistre.jsx; seances_edt_api.py')
case('Mode plage 200 séances','Activer 200 séances et parcourir la pagination; vérifier l’horizon, la limite et la période annoncée.','Chargement explicite borné, sans écraser les résultats d’un autre filtre.','SeancesRegistre.jsx; seances_supervision.py')
case('Date et statut invalides','Dans client API autorisé, soumettre date impossible puis statut inconnu à /supervision/.','400 explicite; aucune mutation.','seances_edt_api.py')
case('Lecteur non gestionnaire','Ouvrir hub avec compte en lecture, puis tenter GET secret QR et liste nominative d’une séance tierce.','Lecture autorisée selon rôle; secret et liste nominative refusés sans garde objet.','seances_edt_api.py',profile='Sécurité')
case('API indisponible et rechargement','Sur environnement contrôlé, provoquer une panne de supervision puis rafraîchir.','Erreur visible, pas de séance ni de compteur inventé; reprise après restauration.','PresencesHub.jsx; SeancesRegistre.jsx')

chapter('3. Ouverture, rotation et validité du QR','Le QR est un jeton de séance partagé et sensible. Ne jamais recopier un token réel dans ce document ni dans un journal public. GET du QR et POST d’ouverture/rotation exigent permission CURP ET droit de gérer l’affectation.')
case('État sans QR','Avec enseignant de la séance prévue ce jour, faire GET /api/presences/seances-edt/{id}/qr/.','actif=false sans divulgation de jeton avant ouverture; aucune écriture.','seances_edt_api.py',profile='Enseignant affecté')
case('Ouvrir QR séance','Dans /presences/poste ou /edt/presences, choisir séance du jour; cliquer Ouvrir QR, relever uniquement ID et expiration masquée.','QR créé et affiché uniquement à l’habilité, fenêtre liée aux horaires de la séance.','PosteBadgeage.jsx; seances_edt_api.py',profile='Enseignant affecté')
case('Rotation QR et ancien jeton','Créer QR A puis régénérer B; tenter scan avec A puis B en environnement isolé.','Ancien refusé/révoqué, nouveau soumis aux mêmes règles; codes expurgés consignés.','seances_edt_services.py; test_seances_edt.py')
case('QR d’une autre séance / date','Rejouer sur séance d’un autre jour et sur affectation inexistante.','Aucune ouverture pour jour non prévu; séance inconnue 404; pas de secret transmis.','seances_edt_api.py')
case('QR annulé ou expiré','Désactiver séance ou dépasser expiration avec horloge de test; scanner l’ancien jeton.','Refus et distinction expiration/révocation si disponible, aucune présence créée.','seances_edt_services.py')
case('GET d’un QR tiers','Avec compte possédant permission globale QR mais sans droit sur la séance, tenter GET et POST.','403 sans secret; le GET n’est pas moins protégé que le POST.','seances_edt_api.py',profile='Sécurité')
case('Format du QR et confidentialité','Capturer l’écran QR autorisé, scanner avec mobile de recette; vérifier journal d’audit et export de capture expurgée.','Le token n’est visible que pendant l’opération, jamais dans preuves, URL partagée ou logs diffusés.','PosteBadgeage.jsx; presences/views.py',profile='Sécurité / enseignant')

chapter('4. Entrées QR, identité et anti-rejeu','Deux canaux à distinguer : poste web POST /api/presences/seances-edt/scan/ et mobile Flutter POST /api/scan/secure/. L’identité est déduite du compte authentifié ; l’application mobile n’est pas la console web.')
case('Étudiant inscrit — entrée','Sur une séance ouverte, connecter un étudiant fictif du groupe et scanner via Flutter avec GPS autorisé; contrôler réponse et liste.','201 ENTREE, canal EDT_LMD, mode QR_AUTOMATIQUE et un seul Pointage de l’acteur.','scan_page.dart; scan_service.dart; seances_edt_services.py',profile='Étudiant')
case('Enseignant désigné','Connecter l’enseignant affecté; scanner sa séance; vérifier type et lien à la séance.','Présence enseignant traçable, sans assimilation à un étudiant.','seances_edt_services.py',profile='Enseignant')
case('Encadrant désigné et non désigné','Tester compte encadrant avec puis sans EncadrantSeance actif sur la même séance.','Habilité admis; non habilité refusé; aucun accès fondé sur nom seul.','seances_edt_services.py; models.py',profile='Encadrant / sécurité')
case('Étudiant d’un autre groupe','Scanner un QR valide d’un groupe étranger avec compte étudiant fictif.','403 ou rejet métier, ETUDIANT_HORS_GROUPE; aucune présence créée.','seances_edt_services.py',profile='Sécurité')
case('Identité forgée dans corps','Depuis client de test, envoyer participant_id, rôle ou inside_geofence mensonger avec QR valide.','Serveur ignore les champs non autoritaires; seul compte connecté est enregistré.','seances_edt_api.py; docs/presences/INTEGRATION-PRESENCES-QR.md',profile='Sécurité')
case('Jeton absent/mal formé/inconnu','Soumettre successivement token manquant, UUID invalide et UUID inexistant via chacun des canaux pertinents.','Refus clair; aucun pointage; vérifier codes legacy et normalisé uniquement si renvoyés.','seances_edt_api.py; seances_edt_services.py')
case('QR trop tôt / hors fenêtre','Faire scan avant ouverture anticipée puis après fin + tolérance sur horloge de test.','TROP_TOT/HORS_FENETRE ou équivalent; aucune entrée tardive non autorisée.','seances_edt_services.py')
case('Double tap immédiat','Scanner deux fois à moins du seuil serveur (défaut 4 s) sur la même séance/personne.','Deuxième scan rejeté DUPLICATE_SCAN / SCAN_DUPLIQUE, sans sortie ni nouvelle ligne.','seances_edt_services.py; docs/audits/FINALISATION_QR_EDT_CI_2026.md')
case('Deuxième scan après seuil','Après délai autorisé, scanner de nouveau avec même compte; vérifier type_sortie.','Sortie selon parcours toggle, type SORTIE_QR et durée calculée.','seances_edt_services.py')
case('Troisième scan et sortie sans entrée','Après entrée + sortie, scanner une troisième fois; sur autre compte sans entrée essayer exit.','ALREADY_SCANNED/DOUBLE_ENTREE et NO_OPEN_SESSION/SORTIE_SANS_ENTREE; aucun nouveau pointage.','seances_edt_services.py; views.py')
case('Rafale concurrente PostgreSQL','Deux appareils ou deux requêtes simultanées pour même personne et QR dans PostgreSQL UTF-8 isolé.','Au plus une entrée effective; aucune sortie immédiate ni pointage doublé; relever codes, verrous et latence.','test_concurrence_postgresql.py; seances_edt_services.py',profile='Sécurité / technique')
case('Révocation pendant la transaction','Sur environnement de test instrumenté, révoquer ou expirer QR après précontrôle mais avant écriture.','Refus après revalidation sous verrou; aucun pointage.','seances_edt_services.py; test_concurrence_postgresql.py',profile='Sécurité / technique')
case('Appareil non autorisé','Scanner avec device_id absent/non reconnu selon la politique effective du type de compte.','Refus motivé si contrôle d’appareil applicable; aucune association fictive.','views.py; models.py')
case('Scan legacy ≠ séance LMD','Comparer QR SessionModule et QR AffectationCreneau via le mobile sur deux jeux isolés.','Chaque jeton suit son canal; résultats legacy ne prouvent pas les règles LMD anti-double-tap.','views.py; seances_edt_services.py')

chapter('5. GPS et géofence','La politique dépend du site géolocalisé de la salle. Rayon et précision sont paramétrables; sans site géolocalisé, le contrôle historique peut être permissif : ce cas exige un arbitrage institutionnel, il ne prouve pas une présence physique.')
case('Site et salle référencés','Dans /presences/configuration, consulter site/salle et rayon approuvé; comparer la FK salle→site.','Le site sélectionné correspond à la salle de la séance; pas de rapprochement homonyme hasardeux.','PresencesGeofence.jsx; geofence.py')
case('GPS précis dans le rayon','Sur simulateur/localisation test avec position autorisée, scanner à l’intérieur du rayon.','Pointage admis si autres règles satisfaites; verdict/ précision selon serveur.','geofence.py; seances_edt_services.py')
case('Hors rayon','Simuler coordonnées hors site sur appareil de test; scanner.','OUT_OF_GEOFENCE / HORS_GEOFENCE, aucun nouveau pointage; contrôle côté serveur.','geofence.py; seances_edt_services.py')
case('Précision au-delà du seuil','Envoyer une position intérieure mais précision supérieure à la configuration (défaut 80 m).','LOCATION_INACCURATE et refus; distance seule ne suffit pas.','geofence.py')
case('Position absente et permission refusée','Retirer permission GPS/couper service; essayer ouverture caméra Flutter puis scan web.','Flutter bloque tant que localisation requise; serveur refuse position absente si site géolocalisé.','scan_page.dart; geofence.py')
case('Site non localisé ou salle ambiguë','Préparer site sans coordonnées puis deux salles homonymes sans FK; contrôler le scan.','Documenter comportement permissif/ambigu, ouvrir réserve sécurité; ne pas déclarer preuve de présence physique.','geofence.py; docs/audits/AUDIT_GLOBAL_INJS_2026.md')
case('Coordonnées protégées','Consulter registre, historique et journal avec lecteur et auditeur; inspecter la réponse exposée.','Pas de latitude/longitude brutes dans les écrans/ réponses publiques; preuve expurgée.','PresencesRegistre.jsx; seances_supervision.py',profile='Sécurité')
case('Changement de site entre deux séances','Tester deux sites géolocalisés avec salles FK différentes, même utilisateur; scanner hors du deuxième.','Périmètre de la séance courante appliqué, pas celui de la première.','geofence.py; test_seances_edt_mobile.py')

chapter('6. Flutter et poste web : permissions, session, réseau','Le mobile Flutter utilise scan_service.dart et check-status, caméra, GPS, badge entrée/sortie, heartbeat; le poste web est distinct. Vérifier Android et web/PWA seulement dans les environnements disponibles, ne pas promettre que toutes les plateformes ont été testées.')
case('Connexion et profil mobile','Connecter compte de recette dans Flutter; consulter configuration mobile puis ouvrir onglet Scanner.','Session et profil conformes; token d’accès non exposé en capture.','login_page.dart; mobile_config_service.dart')
case('Permission caméra refusée puis acceptée','Refuser caméra, ouvrir scanner, puis accorder permission et réessayer.','Message/action utile, aucune requête de scan avant acquisition du QR; caméra reprend si autorisée.','scan_page.dart; camera_permission.dart')
case('Permission localisation refusée puis acceptée','Refuser GPS, naviguer vers scanner puis l’autoriser; surveiller démarrage caméra.','Caméra bloquée quand localisation indisponible selon client; réactivation contrôlée.','scan_page.dart; location_permission.dart')
case('Check-status avant scan','Scanner QR valide avec position; comparer check-status puis résultat du scan.','Statut serveur indique action possible, fenêtre et géofence; check-status seul ne crée pas une présence.','scan_page.dart; scan_service.dart')
case('Application en arrière-plan','Après entrée réelle sur séance de recette, passer en arrière-plan puis revenir; comparer heartbeat.','Continuité dépend de plateforme et réglages; aucune présence supposée si processus suspendu.','background_keepalive.dart; scan_page.dart')
case('Panne réseau au scan et reprise','Couper réseau au moment du scan; rétablir puis interroger état et registre avant nouvelle tentative.','Ne pas déclarer réussite sur erreur réseau; éviter double envoi présumé; état serveur fait foi.','scan_page.dart; scan_service.dart')
case('Déconnexion pendant séance','Se déconnecter pendant une entrée ouverte puis vérifier côté registre; tester reconnexion avec même compte.','Pointage serveur reste consultable selon droits; pas d’identité reprise sur compte tiers.','session_provider.dart; views.py')
case('Poste web entrée et sortie','Dans /presences/poste, choisir séance, ouvrir QR, activer GPS, entrer puis sortir sur jeu isolé.','POST /seances-edt/scan/ pour entrée et /scan/secure/exit/ pour sortie; vérifier même pointage.','PosteBadgeage.jsx; views.py')
case('Mode hors ligne legacy','Tester endpoint /scan/offline-data/ avec jeton remplacé et cache ancien; comparer au scan en ligne.','Aucune preuve d’acceptation hors ligne d’un jeton révoqué; consigner limites et bloquer si cache obsolète.','views.py; offline_cache.py',profile='Sécurité')

chapter('7. Heartbeat, sortie et fin de séance','Le heartbeat observe la position pendant une entrée ouverte, sans créer de nouvelle entrée. Les sanctions legacy SessionModule ont un traitement distinct de la séance EDT; ne pas attribuer à LMD des règles de commande legacy par analogie.')
case('Heartbeat dans périmètre','Après entrée LMD, émettre heartbeat GPS intérieur; comparer pointage ID, compteur et évaluation.','Même pointage mis à jour; DANS_PERIMETRE; aucune ligne d’entrée supplémentaire.','views.py; seances_edt_services.py')
case('Heartbeat hors périmètre confirmé','Émettre positions extérieures successives dans environnement isolé.','HORS_PERIMETRE puis suspicion/sortie auto selon seuil effectif; journal horodaté.','seances_edt_services.py; geofence.py')
case('Heartbeat imprécis ou absent','Pendant entrée ouverte, émettre précision insuffisante puis aucune position sur site configuré.','POSITION_IMPRECISE/POSITION_ABSENTE selon règle; ne pas comptabiliser comme présence physique fiable.','seances_edt_services.py')
case('Heartbeat sans entrée ou sur mauvais jeton','Émettre heartbeat sur un compte sans entrée ouverte puis sur QR remplacé.','Refus sans création d’entrée; réponses distinguables.','views.py; seances_edt_services.py')
case('Sortie volontaire mobile','Après entrée ouverte, appeler sortie sécurisée avec le même compte et QR valide; consulter durée.','Une sortie tracée, type_sortie SORTIE_QR; état final non ouvert.','scan_service.dart; views.py')
case('Sortie hors périmètre','Après entrée admise, déclencher sortie volontaire depuis position extérieure.','Sortie non bloquée par géofence, position signalée dans audit selon contrat; pas de séance laissée ouverte.','docs/presences/INTEGRATION-PRESENCES-QR.md; views.py')
case('Fin de séance et auto-clôture','Laisser entrée ouverte puis clôturer par compte habilité à l’heure autorisée.','Sortie auto de l’entrée ouverte, absents non badgés traités selon règle; QR désactivé et audit conservé.','seances_edt_api.py; seances_edt_services.py')
case('Clôture prématurée ou non habilitée','Tenter autoclore avant fenêtre et avec un autre utilisateur.','Refus selon garde et délai; état du pointage inchangé.','seances_edt_api.py',profile='Sécurité')
case('Notifications et statistiques','Après clôture d’une séance de recette, consulter /stats/alertes/, /stats/notifications/ et taux.','Compteurs issus des pointages effectifs; destinataires selon droit et périmètre; aucun envoi réel hors recette.','stats_api.py; stats_services.py')

chapter('8. Émargement manuel, corrections et absences','Le manuel est une exception tracée avec acteur, motif et statut; le catalogue contient QR_NON_LISIBLE, GPS_INDISPONIBLE, PANNE_RESEAU, PROBLEME_TECHNIQUE, PARTICIPANT_PRESENT_SANS_BADGE, AUTRE avec commentaire. L’émargement de masse suit une sémantique distincte.')
case('Liste nominative de séance','Enseignant affecté : ouvrir /edt/presences?seance=…&date=… et GET /presences/ de la séance.','Attendus, présents, retards, absents et non pointés concordent avec groupe; aucune identité extérieure.','EdtPresences.jsx; seances_edt_api.py',profile='Enseignant')
case('Badgeage unitaire motif QR illisible','Sur /presences/registre, choisir séance et participant non pointé; ouvrir Badger manuellement, choisir QR_NON_LISIBLE.','Mode MANUEL, motif et acteur tracés; pointage unique.','PresencesRegistre.jsx; seances_edt_api.py',profile='Enseignant habilité')
case('Motif absent, inconnu, AUTRE sans commentaire','Soumettre chacun de ces trois essais séparément sur jeu isolé.','400 MOTIF_MANUEL_REQUIS / INCONNU / COMMENTAIRE_MANUEL_REQUIS; aucune correction enregistrée.','seances_edt_services.py')
case('Participant hors groupe en manuel','Tenter unitaire sur ID d’un autre groupe; vérifier liste puis journal.','403 NOT_IN_GROUP; aucun pointage affecté au mauvais groupe.','seances_edt_services.py',profile='Sécurité')
case('Correction d’un QR existant','Sur une présence QR de recette, corriger avec motif et commentaire requis selon cas; relire avant/après.','Mode/acteur/motif et audit conservés; ne pas effacer l’historique du QR.','seances_edt_services.py')
case('Émargement de masse','Sur séance de recette, cocher présence de plusieurs inscrits et exceptions, soumettre avec motif selon geste.','Seuls membres du groupe concernés; journal de chaque modification, aucun succès global si lignes rejetées.','EdtPresences.jsx; seances_edt_api.py')
case('Accès non autorisé à la correction','Avec compte lecture, tenter unitaire, masse et correction d’une séance tierce.','403, pas de contournement via POST direct ni mutation du pointage.','seances_edt_api.py',profile='Sécurité')
case('Absent non badgé et absent justifié','Clôturer avec au moins un inscrit jamais badgé; comparer absent système et correction autorisée documentée.','Mode système non assimilé à manuel/QR; justification traçable; absence non inventée avant clôture.','seances_edt_services.py; models.py')
case('Rattrapage inter-cohorte','Dans /rattrapages, rechercher participant, séance et module de recette; créer puis annuler rattrapage autorisé.','Génération et annulation de présence traçables; pas de substitution silencieuse à un scan QR.','rattrapage_api.py; rattrapage_service.py')

chapter('9. Registre, audit et confidentialité','/presences/registre affiche les pointages liés aux séances publiées. Le journal des événements doit être consulté avec les droits appropriés, sans copie de QR, coordonnées GPS ou données personnelles dans les preuves partagées.')
case('Registre des 200 derniers','Ouvrir /presences/registre sans lien profond; vérifier chargement explicite 200 et total vs résultat API.','Périmètre et plafonds expliqués; pas d’affirmation de couverture historique complète sur cette seule vue.','PresencesRegistre.jsx; seances_edt_api.py')
case('Période et filtres combinés','Choisir Du/Au, nom fictif, groupe, type étudiant/enseignant/encadrant, mode QR/MANUEL et séance.','Filtrage serveur et URL cohérents; aucun pointage d’une autre séance.','PresencesRegistre.jsx; seances_supervision.py')
case('Statut et durée','Comparer entrée, sortie, retard, absent, durée et type_sortie dans liste et détail sur jeu isolé.','Heures et durée cohérentes; sortie automatique distincte de sortie volontaire.','seances_supervision.py; models.py')
case('Audit QR et refus','Ouvrir /presences/audit après QR ouvert, scan accepté, refus hors groupe/GPS et correction manuelle.','Journal horodaté avec acteur et action, sans secret QR ni coordonnées brutes dans vue non habilitée.','PresencesAudit.jsx; views.py')
case('Logs historiques et masquage','Contrôler échantillon d’anciens journaux uniquement sur copie isolée via compte auditeur habilité.','Champs secrets masqués en API; historique inchangé en base, incident documenté si fuite.','views.py; docs/audits/AUDIT_GLOBAL_INJS_2026.md',profile='Audit / sécurité')
case('Lien séance et source ECUE','Depuis hub → séance → registre → pointage → fiche autorisée, comparer année, groupe, ECUE et type de personne.','Chaîne sans mélange d’années; lien ECUE manquant signalé comme réserve, non imputé.','PresencesHub.jsx; seances_edt_services.py')
case('Export et accès données personnelles','Si export métier disponible sur rôle habilité, comparer nombre de lignes, droits, masquage et période à l’écran.','Aucun export non autorisé; preuve anonymisée, jamais journal brut ni token.','presences/urls.py; exports/',profile='Audit / sécurité')

chapter('10. Résilience, sécurité et arbitrage final','Cette matrice est un protocole, pas une homologation. Les tests PostgreSQL historiques documentés ne certifient ni les terminaux réels, ni la production, ni la politique géofence de l’institution. Chaque écart critique doit bloquer un GO.')
case('Deux utilisateurs et deux séances simultanées','Badger deux comptes sur séances proches, dont un site distinct, avec concurrence contrôlée.','Pas de croisement de personne, séance, site, groupe ou audit; aucune double entrée.','test_concurrence_postgresql.py; seances_edt_services.py')
case('Fenêtres serveur et horloge appareil','Décaler horloge mobile sur appareil de recette sans changer horloge serveur; badger près des bornes.','Serveur décide la fenêtre/horodatage; client ne force pas statut.','seances_edt_services.py; scan_page.dart')
case('Rejeu après clôture et révocation','Réutiliser ancienne capture de QR après clôture puis après régénération et sur autre année.','Tous les rejets motivés; aucun pointage créé avec token périmé.','seances_edt_services.py; views.py')
case('Rate limit et bruit','Déclencher une rafale contrôlée de scans invalides sans saturer l’environnement; conserver HTTP.','Limitation ScanRateThrottle appliquée; absence de fuite de secrets et aucun pointage.','seances_edt_api.py; authentication/throttles.py')
case('Panne backend pendant scan','Couper l’API sur environnement isolé entre check-status et scan puis rétablir; consulter historique serveur.','Message de reprise sans faux succès ni double soumission aveugle.','scan_page.dart; scan_service.dart')
case('Contrat web/Flutter','Comparer réponses legacy code/detail et champs LMD code_normalise/message/action_recommandee dans clients web et mobile.','Messages compatibles, aucun 500 dû au changement de contrat; absence de champ ne devient pas présence.','PresencesContrat.jsx; seances_edt_services.py')
case('Bilan institutionnel','Réconcilier EDT publié, séance, QR, pointages, registre, audit, statistiques, S1/S2, GPS et appareils réels; remplir PV.','GO seulement après exécution des cas applicables, correction des P1, preuve réelle, calendrier et visas; sinon ajourner.','Ensemble du module; docs/audits/FINALISATION_QR_EDT_CI_2026.md',profile='Responsable métier / sécurité / DSI',evidence='PV signé et daté, tickets et pièces expurgées stockées dans le référentiel officiel.')

N=sum(len(c['cases']) for c in CHAPTERS)
assert len(CHAPTERS)==10 and len({x['id'] for c in CHAPTERS for x in c['cases']})==N
PREFACE=[
('Objet et statut','Manuel démo de test de bout en bout, construit à partir de code React, Django et Flutter du dépôt. Les cas décrivent des actions à réaliser, des résultats attendus et des preuves, PAS des validations constatées. Un inventaire fini ne peut énumérer absolument tous les états, appareils et changements futurs : compléter la matrice lors de chaque évolution.'),
('Architecture réelle','Console web React (frontend/src/pages/presences, EdtPresences.jsx), API Django /api/presences/seances-edt/… et /api/scan/secure/…, application Flutter qr_badge_mobile pour scan mobile. GET INJS APP publie les séances; Présences QR rattache les pointages à edts.AffectationCreneau. Flutter ne pilote pas l’EDT.'),
('Limites de sécurité','Le QR est partagé par séance, non preuve à lui seul de présence physique. Sans site géolocalisé, la vérification de périmètre peut être permissive. Les tests de concurrence PostgreSQL locaux historiques et le code ne certifient ni les appareils réels ni la production. Le calendrier annuel GET INJS APP n’est pas présumé homologué.'),
('Consigne de confidentialité','Aucun token QR, identifiant de connexion, cookie, GPS brut ou nom réel dans le manuel, les exports diffusés ou les captures partagées. Employer des données fictives seulement sur environnement isolé, préserver les journaux et les données institutionnelles en production; ne pas effectuer de déploiement pour ce manuel.'),
('Mode de constat','Pour chaque PQR-xxx, consigner date/heure, version, appareil, séance et profil (identifiants fictifs), attendu/observé, HTTP et code, statut Non exécuté/Réussi/Échec/Bloqué/N/A, ticket et preuve externe expurgée. Les cases à cocher et visas sont vierges. Aucun résultat ancien n’est présenté comme une exécution de cette campagne.'),
]
FLOW=[
('Parcours A — étudiant LMD','Inscription validée → groupe/maquette → EDT validé/publié → occurrence de séance → QR ouvert par enseignant autorisé → connexion Flutter et GPS → check-status → scan entrée → heartbeat → sortie volontaire/auto → registre nominatif → audit → statistiques et visa.'),
('Parcours B — exceptions et sécurité','Même séance avec compte hors groupe, enseignant non affecté, QR périmé, GPS absent/hors zone et appareil non autorisé → refus motivés sans entrée; si présence réelle malgré panne, émargement manuel motivé par gestionnaire → contrôle de l’acteur et historique.'),
('Parcours C — web / mobile / legacy','Comparer poste web et mobile Flutter sur le même pointage LMD puis vérifier séparément une SessionModule legacy : deux canaux, même module de géofence mais règles de cycle à mesurer individuellement. Un test legacy réussi ne qualifie pas le LMD.'),
]
RUNBOOK=[
('Fiche de séance et environnement','Référence de recette : ______ ; URL isolée / commit : ______ ; build Flutter / OS / modèle d’appareil : ______ ; année et semaines S1/S2 approuvées : ______ ; date et plage horaire : ______ ; séance et groupe fictifs : ______ ; site et rayon approuvés : ______ ; comptes étudiant, enseignant, encadrant, secrétariat : ______. Jamais de mot de passe ni de jeton ici.'),
('Jeu minimal autorisé','Préparer deux groupes, deux étudiants dont un hors groupe, une séance publiée avec enseignant désigné et encadrant habilité, une séance brouillon et une annulée, deux salles sur sites géolocalisés distincts, un site sans coordonnées pour test de réserve, deux appareils et deux horaires d’essai. Utiliser l’horloge instrumentée/fixtures en test pour fenêtres et expirations, jamais modifier la production.'),
('Avant / après chaque cas','Avant : capturer compte des Pointage, statut QR, audit et heure serveur. Pendant : noter requête/HTTP/canal, sans secret. Après : comparer pointage ID, entrée, sortie, type, mode, motif, compteur et absence de mutation sur refus; joindre seulement une référence de pièce expurgée.'),
('Règle GO / NO-GO','GO uniquement si QR, identité et garde objet, concurrence PostgreSQL, géofence approuvée, limites S1/S2, terminaux réels et confidentialité passent en recette avec preuves et PV signé. Un échec P1, une politique permissive non arbitrée, une pièce absente ou un test non exécuté impose NO-GO/ajournement, pas de case Réussi forcée.'),
]
SOURCES=['frontend/src/menu/arborescence.js; frontend/src/App.jsx','frontend/src/pages/presences/{PresencesHub,SeancesRegistre,PosteBadgeage,PresencesRegistre,PresencesAudit,PresencesGeofence,PresencesContrat}.jsx; frontend/src/pages/EdtPresences.jsx','backend/presences/{urls.py,seances_edt_api.py,seances_edt_services.py,seances_supervision.py,geofence.py,views.py,models.py,rattrapage_api.py}','backend/presences/{test_seances_edt.py,test_seances_edt_mobile.py,test_concurrence_postgresql.py,test_seances_supervision.py}; tests.py','qr_badge_mobile/lib/{pages/scan_page.dart,services/scan_service.dart,services/background_keepalive.dart}','docs/presences/INTEGRATION-PRESENCES-QR.md; docs/audits/FINALISATION_QR_EDT_CI_2026.md (résultats historiques, non reproduits ici)']

# DOCX
navy=RGBColor(18,48,84);blue=RGBColor(35,92,140)
d=Document();sec=d.sections[0];sec.top_margin=Cm(2);sec.bottom_margin=Cm(1.8);sec.left_margin=Cm(2.1);sec.right_margin=Cm(2.1)
styles=d.styles;styles['Normal'].font.name='Calibri';styles['Normal'].font.size=Pt(10)
for s,size in [('Title',22),('Heading 1',16),('Heading 2',12)]:styles[s].font.name='Calibri';styles[s].font.size=Pt(size);styles[s].font.color.rgb=navy
p=d.add_paragraph(style='Title');p.alignment=WD_ALIGN_PARAGRAPH.CENTER;p.add_run(TITLE)
p=d.add_paragraph('INJS • édition documentaire de recette 2026 • version initiale non exécutée');p.alignment=WD_ALIGN_PARAGRAPH.CENTER
p=d.add_paragraph(f'{N} scénarios numérotés | 10 chapitres | DOCX et PDF issus de la même source');p.alignment=WD_ALIGN_PARAGRAPH.CENTER
p=d.add_paragraph('STATUT : PROTOCOLE À EXÉCUTER — AUCUNE VALIDATION MÉTIER PRÉREMPLIE');p.alignment=WD_ALIGN_PARAGRAPH.CENTER;p.runs[0].bold=True
for label,text in PREFACE:d.add_heading(label,1);d.add_paragraph(text)
d.add_heading('Parcours de bout en bout',1)
for label,text in FLOW:d.add_heading(label,2);d.add_paragraph(text)
d.add_heading('Fiche d’exécution et critères d’arrêt',1)
for label,text in RUNBOOK:d.add_heading(label,2);d.add_paragraph(text)
d.add_heading('Sommaire des chapitres',1)
for ch in CHAPTERS:d.add_paragraph(f"{ch['name']} — {len(ch['cases'])} cas")
d.add_page_break()
for ch in CHAPTERS:
 d.add_heading(ch['name'],1);d.add_paragraph(ch['intro'])
 for x in ch['cases']:
  d.add_heading(f"{x['id']} — {x['title']}",2)
  for label,key in [('Profil','profile'),('Procédure','steps'),('Résultat attendu (à vérifier)','expected'),('Preuve à conserver','evidence'),('Source technique','source')]:
   p=d.add_paragraph();p.add_run(label+' : ').bold=True;p.add_run(x[key])
  p=d.add_paragraph('Constat : ☐ Non exécuté    ☐ Réussi    ☐ Échec    ☐ Bloqué    ☐ N/A   |  Ticket / preuve : ___________________')
  p.paragraph_format.space_after=Pt(10)
d.add_heading('Matrice de clôture et visas',1)
for line in ['Environnement / version / commit : __________________________________________','Année académique et calendrier officiel approuvé : __________________________','Jeu de données de recette / isolement : ____________________________________',f'Cas prévus : {N}   Exécutés : ______   Réussis avec preuve : ______   Échecs : ______   Bloqués : ______   N/A justifiés : ______','Réserves et tickets bloquants : _____________________________________________','Décision (à cocher après revue humaine) : ☐ Validé   ☐ Refusé   ☐ Ajourné','Responsable métier : __________________  Date : __________  Signature/PV : __________','Responsable technique : ________________  Date : __________  Signature/PV : __________']:
 d.add_paragraph(line)
d.add_heading('Sources auditées (inventaire de code, non recette)',1)
for s in SOURCES:d.add_paragraph(s,style='List Bullet')
footer=sec.footer.paragraphs[0];footer.alignment=WD_ALIGN_PARAGRAPH.CENTER;footer.text='PRÉSENCES QR • protocole de recette — non exécuté • INJS2026'
OUT.mkdir(parents=True,exist_ok=True);d.save(OUT/f'{BASE}.docx')

# PDF, même structure et mêmes champs (sans utiliser Word/LibreOffice).
pdfmetrics.registerFont(TTFont('DejaVu','/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'))
pdfmetrics.registerFont(TTFont('DejaVuBold','/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'))
ss=getSampleStyleSheet();ss.add(ParagraphStyle(name='GTTitle',fontName='DejaVuBold',fontSize=17,leading=24,textColor=HexColor('#123054'),spaceAfter=16,alignment=TA_CENTER));ss.add(ParagraphStyle(name='GT1',fontName='DejaVuBold',fontSize=13,leading=18,textColor=HexColor('#123054'),spaceBefore=15,spaceAfter=7));ss.add(ParagraphStyle(name='GT2',fontName='DejaVuBold',fontSize=10,leading=15,textColor=HexColor('#235c8c'),spaceBefore=9,spaceAfter=5));ss.add(ParagraphStyle(name='GTBody',fontName='DejaVu',fontSize=8.6,leading=13,spaceAfter=5));ss.add(ParagraphStyle(name='GTSmall',fontName='DejaVu',fontSize=7.7,leading=11,spaceAfter=7));ss.add(ParagraphStyle(name='GTWarn',fontName='DejaVuBold',fontSize=8.7,leading=13,textColor=HexColor('#9c3027'),spaceAfter=10))
def pp(text,sty='GTBody'):return Paragraph(escape(text).replace('\n','<br/>'),ss[sty])
def labelled(l,v):return Paragraph(f'<b>{escape(l)} :</b> {escape(v)}',ss['GTBody'])
story=[pp(TITLE,'GTTitle'),pp('INJS • édition documentaire de recette 2026 • version initiale non exécutée'),pp(f'{N} scénarios numérotés | 10 chapitres | DOCX et PDF issus de la même source'),pp('STATUT : PROTOCOLE À EXÉCUTER — AUCUNE VALIDATION MÉTIER PRÉREMPLIE','GTWarn')]
for l,t in PREFACE:story.extend([pp(l,'GT1'),pp(t)])
story.append(pp('Parcours de bout en bout','GT1'))
for l,t in FLOW:story.extend([pp(l,'GT2'),pp(t)])
story.append(pp('Fiche d’exécution et critères d’arrêt','GT1'))
for l,t in RUNBOOK:story.extend([pp(l,'GT2'),pp(t)])
story.append(pp('Sommaire des chapitres','GT1'))
for ch in CHAPTERS:story.append(pp(f"{ch['name']} — {len(ch['cases'])} cas"))
story.append(PageBreak())
for ch in CHAPTERS:
 story.extend([pp(ch['name'],'GT1'),pp(ch['intro'])])
 for x in ch['cases']:
  first=[pp(f"{x['id']} — {x['title']}",'GT2'),labelled('Profil',x['profile']),labelled('Procédure',x['steps'])]
  story.append(KeepTogether(first))
  for label,key in [('Résultat attendu (à vérifier)','expected'),('Preuve à conserver','evidence'),('Source technique','source')]:story.append(labelled(label,x[key]))
  story.append(pp('Constat : [ ] Non exécuté   [ ] Réussi   [ ] Échec   [ ] Bloqué   [ ] N/A   |   Ticket / preuve : ___________________','GTSmall'))
story.append(pp('Matrice de clôture et visas','GT1'))
for line in ['Environnement / version / commit : __________________________________________','Année académique et calendrier officiel approuvé : __________________________','Jeu de données de recette / isolement : ____________________________________',f'Cas prévus : {N}   Exécutés : ____   Réussis avec preuve : ____   Échecs : ____   Bloqués : ____   N/A justifiés : ____','Réserves et tickets bloquants : _____________________________________________','Décision : [ ] Validé   [ ] Refusé   [ ] Ajourné (après revue humaine)','Responsable métier : __________________  Date : __________  Signature/PV : __________','Responsable technique : ________________  Date : __________  Signature/PV : __________']:story.append(pp(line))
story.append(pp('Sources auditées (inventaire de code, non recette)','GT1'))
for s in SOURCES:story.append(pp('• '+s,'GTSmall'))
def decoration(canvas,doc):
 canvas.saveState();canvas.setFont('DejaVu',8);canvas.setFillColor(HexColor('#5c7086'));canvas.drawString(42,27,'PRÉSENCES QR • protocole non exécuté');canvas.drawRightString(A4[0]-42,27,f'Page {doc.page}');canvas.restoreState()
SimpleDocTemplate(str(OUT/f'{BASE}.pdf'),pagesize=A4,rightMargin=43,leftMargin=43,topMargin=42,bottomMargin=48,title=TITLE,author='INJS • protocole de recette').build(story,onFirstPage=decoration,onLaterPages=decoration)
print('Créés',N,'cas',len(CHAPTERS),'chapitres',OUT)
