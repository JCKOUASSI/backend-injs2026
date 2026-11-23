"""DOCX/PDF synchronisés : protocole de recette GET INJS APP, sans exécution ni données réelles."""
from pathlib import Path
from xml.sax.saxutils import escape
from docx import Document
from docx.shared import Cm, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.colors import HexColor, white
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.pagesizes import A4

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'dossier_trvx/Manuel_jeu_GETINJSAPP2026'
BASE='Manuel_Demo_Recette_GET_INJS_APP_2026'
CHAPTERS=[]

def chapter(name,intro):
 CHAPTERS.append({'name':name,'intro':intro,'cases':[]})
def case(title,steps,expected,source,profile='Planificateur',evidence=None):
 n=sum(len(c['cases']) for c in CHAPTERS)+1
 CHAPTERS[-1]['cases'].append(dict(id=f'GET-{n:03d}',title=title,steps=steps,expected=expected,source=source,profile=profile,evidence=evidence or 'Capture expurgée, identifiant de campagne/EDT, réponse ou export et horodatage.'))

chapter('1. Accès, préflight et accueil', 'Préparer deux comptes de recette distincts (planification et direction), un compte lecture et un compte non autorisé. La navigation React est une interface web ; Flutter sert au badgeage/QR mobile, pas à la génération GET. Vérifier les droits côté API, pas seulement l’affichage des boutons.')
case('Session planificateur et tableau de bord','Se connecter avec le compte autorisé; ouvrir /get-injs-app; relever année courante et compteurs; comparer aux données de recette.','Page charge sans valeurs inventées; liens vers Génération, Import, Dimensionnement et EDT fonctionnent.','GetInjsApp.jsx; App.jsx',evidence='Capture des compteurs expurgée et réponse API constatée.')
case('Année vide ou données absentes','Choisir un environnement de recette sans campagne ni EDT; ouvrir le tableau de bord et la grille.','Un état vide explicite remplace toute statistique fictive; aucune opération n’est réputée exécutée.','GetInjsApp.jsx; Edts.jsx')
case('Session expirée ou anonyme','Déconnecter le compte; ouvrir les routes GET et solliciter une API de lecture via le navigateur ou le client de recette.','Redirection/401 attendu selon couche; aucune donnée métier exposée.','App.jsx; edts/permissions.py',profile='Lecteur / sécurité')
case('Droits de lecture et écriture distincts','Avec un compte lecture, consulter /edt puis tenter une API POST de planification sur un jeu isolé.','Consultation autorisée seulement si garde du compte le permet; mutation refusée (403), rien créé.','edts/permissions.py; App.jsx',profile='Lecteur / sécurité')
case('Direction et publication','Avec le planificateur puis la direction, essayer valider/publier un EDT de recette admissible.','La validation/publication exige le droit serveur de validation; ne pas assimiler un bouton visible à une permission.','edts/permissions.py; api_lmd.py',profile='Direction / sécurité')
case('Conception téléchargeable','Ouvrir /edt/conception et télécharger Conception-GET-INJS.txt; vérifier téléchargement et contenu non vide.','Document technique accessible si autorisé; erreur affichée si ressource absente.','Conception.jsx; api_getinjs.py',profile='Lecteur')

chapter('2. Référentiels et préparation LMD','Avant toute écriture, vérifier année officielle, calendrier approuvé, filières/formations, niveaux L1–M2, semestres S1–S10 selon référentiel, maquettes UE/ECUE, affectations, enseignants, créneaux et salles. Ne pas créer de dates semestrielles fictives.')
case('Année académique et cohérence','Ouvrir /edt/referentiels; sélectionner l’année de recette; comparer son libellé et son état avec /scolarite/ref/annees/.','Les données affichées correspondent à l’année choisie; aucun mélange entre années.','Referentiels.jsx; api_getinjs.py')
case('Filières, formations et niveaux','Comparer les référentiels GET aux objets INJS de recette; noter codes et niveaux rattachés.','Les identifiants nécessaires au périmètre existent; toute incohérence est bloquante pour le scénario concerné.','Referentiels.jsx; edts/moteur/besoins.py')
case('Maquette UE/ECUE et volumes','Comparer les volumes CM/TD/TP, semestres et affectations avec la maquette approuvée.','Les besoins du moteur sont traçables à la maquette; volume absent est signalé et non planifié silencieusement.','edts/moteur/besoins_maquette.py; edts/moteur/annee.py')
case('Enseignants et disponibilités','Contrôler enseignants, affectations et indisponibilités sur l’année; préparer un chevauchement de recette.','Une indisponibilité est respectée ou le blocage est visible; aucune affectation fantôme.','edts/urls.py; edts/moteur/contraintes.py')
case('Salles et capacités','Vérifier salles actives, capacités et types CM/TD/TP; préparer une salle insuffisante.','Affectation salle/groupe compatible ou non-placement motivé; aucun surbooking non signalé.','Referentiels.jsx; edts/moteur/generation.py')
case('Créneaux et samedi','Comparer les créneaux types avec le canevas officiel; vérifier la disponibilité du samedi.','L’option samedi respecte les créneaux configurés; horaires hors canevas non créés par présomption.','edts/urls.py; GenerationAnnuelle.jsx')
case('Calendrier S1/S2 non défini','Préparer une année avec besoins des deux semestres sans bornes officielles; prévisualiser sans persister.','Un calendrier institutionnel manquant ne doit pas être inventé; noter motif de blocage/non-conformité.','edts/moteur/annee.py',evidence='Rapport de prévisualisation et décision institutionnelle sur les dates, sans dates fabriquées.')

chapter('3. Population et import des inscrits','Deux origines : inscriptions administratives validées (Base) et fichier externe (Import). Utiliser uniquement des matricules fictifs isolés; aucune donnée fictive en production. Modèle CSV : matricule;nom;prenoms;sexe;date_naissance;filiere_code;formation;niveau;semestre;groupe;vague;statut. Obligatoires : matricule, nom, formation, niveau.')
case('Population issue de la base','Valider des inscriptions de recette via Scolarité; ouvrir /edt/etudiants-inscrits; choisir l’année.','Seules inscriptions administratives validées remontent; source Base, effectifs cohérents.','EtudiantsInscrits.jsx; api_getinjs.py')
case('Modèle CSV et analyse sans écriture','Télécharger le modèle CSV depuis /edt/import-etudiants; remplir un fichier fictif; choisir l’année; dans /edt/generation-annuelle utiliser Analyser.','Colonnes reconnues, compteurs et rejets motivés; aucune inscription nouvelle à l’analyse.','ImportEtudiants.jsx; GenerationAnnuelle.jsx; import_inscrits.py')
case('Import CSV valide','Importer le fichier de recette en UTF-8 et vérifier le rapport lignes lues/valides/créées; consulter le journal.','Chaque matricule valide figure dans l’année cible; le rapport explique créations/mises à jour.','api_getinjs.py; import_inscrits.py')
case('Import XLSX ou XLSM','Reprendre un jeu de recette équivalent en XLSX/XLSM; sélectionner le fichier et comparer les lignes reconnues.','Format supporté si conforme; lignes et motifs concordants avec CSV, sans perte silencieuse.','ImportEtudiants.jsx; import_inscrits.py')
case('Réimport identique','Importer deux fois le même fichier de recette sur la même année; comparer lignes, matricules et compteurs.','Aucun doublon de la clé année + matricule; mises à jour documentées.','import_inscrits.py; tests/test_import_inscrits.py')
case('Même matricule dans Base et Import','Sur jeu isolé, placer un matricule identique dans inscription validée et fichier; consulter la population.','Population fusionnée sans double compte; vérifier priorité Base et résultat réel.','api_getinjs.py; tests/test_inscrits_population.py')
case('Colonne obligatoire absente','Supprimer formation ou niveau du modèle; lancer Analyser puis Importer.','Refus et liste des colonnes manquantes; aucune création partielle non annoncée.','import_inscrits.py; api_getinjs.py')
case('Lignes invalides et matricule manquant','Inclure une ligne sans matricule, une formation inconnue, et une ligne valide; analyser puis importer sur environnement isolé.','Rejets ligne par ligne motivés, validées distinguées; aucune identité inventée.','import_inscrits.py; ImportEtudiants.jsx')
case('Fichier absent, trop volumineux, extension inconnue','Tester séparément aucun fichier, >20 Mo et extension non admise avec année valide.','Refus explicite (413 pour dépassement de 20 Mo selon API); aucune inscription créée.','api_getinjs.py; ImportEtudiants.jsx')
case('Année absente ou inconnue','Tenter import sans année puis avec année inexistante via client de recette autorisé.','400/404 selon erreur d’année; pas d’import transversal.','api_getinjs.py')
case('Reconstruction du parcours','Dans /edt/import-etudiants, comparer Reconstruire le parcours décoché/coché sur deux jeux isolés.','Groupes/vagues manquants créés uniquement si option et référentiels valides; vérifier rapport.','ImportEtudiants.jsx; import_inscrits.py')
case('Import avec génération enchaînée','Sur jeu approuvé, cocher Générer les EDT après import; choisir semestre unique puis relancer sur autre jeu avec Toute l’année.','Comparer campagne créée, statut final et périmètre réellement généré; ne jamais inférer que import réussi = EDT publiés.','ImportEtudiants.jsx; api_getinjs.py')
case('Liste filtrée et pagination','Dans /edt/etudiants-inscrits, filtrer année, formation, niveau et recherche par matricule fictif; parcourir pages.','Total et pagination cohérents; aucune entrée d’une autre année; masquer données sensibles dans preuve.','EtudiantsInscrits.jsx; api_getinjs.py')

chapter('4. Dimensionnement et constitution','Le besoin de groupes découle des effectifs validés, de la capacité choisie, des salles et de la maquette. La constitution ne répartit pas les étudiants : cette opération reste dans Scolarité → Groupes.')
case('Capacité cible et KPI','Ouvrir /edt/dimensionnement; choisir année et capacité cible; comparer effectif, promotions, déficit, EDT et heures au jeu source.','Aucun volume imposé à l’avance; recalcul quand la capacité change.','Dimensionnement.jsx; edts/moteur/dimensionnement.py')
case('Promotion sans groupe','Préparer promotion valide sans groupe; charger dimensionnement.','Anomalie/ déficit visible; la génération ne présume pas une répartition inexistante.','Dimensionnement.jsx; edts/moteur/dimensionnement.py')
case('Simulation de constitution','Cliquer Prévisualiser la constitution; conserver le nombre de groupes avant/après.','Plan proposé sans création; aucune écriture en simulation.','Dimensionnement.jsx; api_getinjs.py')
case('Constitution confirmée','Confirmer la constitution sur l’environnement isolé; vérifier nombre créé puis répartir via Scolarité → Groupes.','Groupes créés selon plan; étudiants non répartis automatiquement; traçabilité du résultat.','Dimensionnement.jsx; edts/moteur/constitution.py')
case('Constitution interdite en lecture','Avec un compte lecture seule, tenter simulation et création; comparer réponse.','Écriture refusée par API; aucun nouveau groupe.','api_getinjs.py; edts/permissions.py',profile='Lecteur / sécurité')

chapter('5. Génération manuelle et prévisualisation','Route /edt/generation-annuelle : cases à cocher filières, formations, niveaux, groupes et semestres, plus case Tout sélectionner (options visibles). Le mode manuel exige formation/filière, niveau, groupe et semestre et une prévisualisation du périmètre exact avant écriture.')
case('Sélection « tout » visible','Choisir une filière; cocher Tout sélectionner pour les formations visibles, niveaux, groupes et semestres; vérifier compteurs; décocher.','Seules options visibles sont sélectionnées; aucune sélection cachée n’entre dans le périmètre sans contrôle.','GenerationAnnuelle.jsx')
case('Périmètre minimal L1 S1','Choisir année, une formation, niveau L1, groupe réel, semestre S1, semaines approuvées; Prévisualiser sans persister.','Bilan par groupe et totaux visibles; vérifier EDT persistés inchangés.','GenerationAnnuelle.jsx; edts/moteur/annee.py')
case('Périmètre incomplet','Ne sélectionner qu’une formation et cliquer Génération manuelle ou Prévisualiser.','Message demandant formation/filière + niveau + groupe + semestre; aucune campagne créée.','GenerationAnnuelle.jsx')
case('Groupe hors périmètre','Sélectionner groupe puis changer niveau ou formation; prévisualiser.','Le groupe est réinitialisé ou demande de correction; pas de génération sur un groupe caché.','GenerationAnnuelle.jsx')
case('Aperçu devenu obsolète','Prévisualiser puis changer semaines, contraintes ou groupe; lancer Génération manuelle.','Blocage et nouvelle prévisualisation obligatoire; aucune campagne créée sur l’ancien aperçu.','GenerationAnnuelle.jsx')
case('Persistance manuelle après aperçu','Sur le périmètre approuvé exact, prévisualiser puis cliquer Lancer la génération manuelle.','Campagne créée, données prêtes, démarrage asynchrone; vérifier bilan, historique, EDT brouillon et séances réellement placées.','GenerationAnnuelle.jsx; api_getinjs.py')
case('S1 puis S2 distincts','Sur calendrier approuvé, préparer semestre S1 et semaines correspondantes, puis S2 et autres semaines; comparer grilles.','Aucun chevauchement indu; chaque semestre a ses semaines et volumes vérifiés; aucune date inventée.','edts/moteur/annee.py; Edts.jsx')
case('Plusieurs semaines avec semestre unique','Prévisualiser un seul semestre sur deux semaines officielles; confronter séances/ heures attendues et récurrences effectives.','Aucune couverture COMPLETE si occurrences ou heures réelles divergent des besoins.','edts/moteur/annee.py')
case('CM, TD et TP','Sur maquette de recette avec les trois natures, générer après contrôle des ressources.','CM mutualisés selon besoin et capacité; TD/TP par groupe; heures et séances comparées au référentiel.','GenerationAnnuelle.jsx; edts/moteur/besoins.py')
case('Samedi et pause méridienne','Faire deux aperçus identiques sauf options samedi et Éviter la pause 12h–14h.','Grilles respectent les options; vérifier différences et éventuels besoins non placés.','GenerationAnnuelle.jsx; edts/moteur/annee.py')
case('Quota hebdomadaire','Fixer max séances par groupe/semaine plus bas que le besoin; prévisualiser.','Séances excédentaires restent attendues et non placées, pas comptées comme couvertes.','edts/moteur/annee.py; GenerationAnnuelle.jsx')
case('Capacité et disponibilité insuffisantes','Préparer manque de salle puis enseignant indisponible; prévisualiser séparément.','Plan PARTIEL/IMPOSSIBLE selon résultat, motif par groupe et séance non placée; pas de faux succès.','edts/moteur/annee.py; contraintes.py')
case('Conflits croisés','Préparer deux groupes en concurrence pour salle ou enseignant sur un même créneau; prévisualiser.','Aucun double placement non signalé; détecteur de conflits et bilan concordent.','edts/moteur/contraintes.py; edts/services.py')

chapter('6. Génération automatique de toute l’année','Bouton distinct « Lancer la génération automatique (toute l’année) ». Il ignore les sélections manuelles et demande confirmation; il peut remplacer des séances générées existantes. Sans calendrier multi-semestre officiel, un lancement ne prouve pas une année complète valide.')
case('Annulation de confirmation','Choisir année puis cliquer Automatique et annuler la boîte de confirmation.','Aucune campagne et aucune séance modifiée.','GenerationAnnuelle.jsx')
case('Périmètre annuel annoncé','Conserver une sélection manuelle restreinte, confirmer le bouton Automatique sur année isolée.','Campagne porte périmètre vide = toutes formations/niveaux/groupes/semestres selon backend; vérifier bilan de tous les groupes.','GenerationAnnuelle.jsx; api_getinjs.py')
case('Calendrier multi-semestre manquant','Sur année complète S1/S2 sans calendrier officiel exploitable, confirmer dans environnement isolé puis inspecter résultat.','Blocage ou PARTIEL/IMPOSSIBLE motivé, jamais qualification COMPLETE sur répartition arbitraire.','edts/moteur/annee.py')
case('Relance et remplacement','Capturer nombres et IDs avant/après une seconde génération sur le même périmètre isolé.','Anciennes séances générées traitées selon règle de remplacement; pas de doublon actif ni suppression de données non ciblées.','api_getinjs.py; edts/moteur/annee.py')
case('Exécution longue / délai UI','Lancer une campagne volumineuse de recette avec contrôle de charge; suivre statut, puis historique au-delà du délai client.','Démarrage asynchrone; attendre résultat réel; après 20 minutes UI avertit de consulter historique, sans déclarer l’échec ni le succès.','GenerationAnnuelle.jsx; api_getinjs.py')
case('Double démarrage / concurrence','Sur jeu isolé, lancer deux campagnes chevauchantes avec utilisateurs habilités; conserver statuts et EDT.','Respect du verrouillage/contrôle de concurrence; aucune duplication ni état incohérent; consigner toute anomalie.','edts/moteur/campagnes.py; tests/test_campagnes.py')

chapter('7. Campagnes, publication et versions','Vérifier étapes données prêtes → démarrer → statut/résultat → valider → publier. La case « Publier directement » peut provoquer validation puis publication après calcul : ne l’activer qu’avec un compte habilité et une approbation réelle.')
case('Campagne manuelle dans /edt/campagnes','Créer une campagne avec année, libellé, semaines et périmètre de recette; relire sa fiche.','Campagne traçable avec auteur, année et paramètres; aucune exécution implicite.','CampagnesGeneration.jsx; api_getinjs.py')
case('États et historique','Passer aux états permis puis démarrer; consulter /statut/, /resultat/ et historique.','États et horodatages cohérents; erreurs visibles et périmètre sauvegardé.','CampagnesGeneration.jsx; api_getinjs.py')
case('Validation avec audit bloquant','Préparer campagne/EDT comportant un manque bloquant; tenter validation depuis compte autorisé.','Refus avec violations et motif; aucun statut validé/publication.','VersionsPublication.jsx; api_lmd.py')
case('Publication par direction','Sur EDT complet, audité et approuvé, valider puis publier avec compte Direction; consulter /edt/versions.','Statut et date reflètent la transition, séances publiées visibles seulement après publication.','VersionsPublication.jsx; api_lmd.py',profile='Direction')
case('Publication directe non autorisée','Activer Publier directement avec un planificateur sans droit de validation sur jeu isolé.','Étape de validation/publication refusée explicitement; vérifier état réel de la campagne après erreur.','GenerationAnnuelle.jsx; edts/permissions.py')
case('Versions et audit de version','Sélectionner une version dans /edt/versions; lire audit, auteur et dates; comparer deux versions du même EDT.','Historique et audit cohérents; ne pas confondre version BROUILLON et version PUBLIEE.','VersionsPublication.jsx; api_lmd.py')
case('Historique paginé / erreur','Générer ou utiliser un historique de recette >15 événements; parcourir; simuler erreur d’accès au résultat.','Navigation sans perte de lignes; message d’erreur explicite, pas de compteurs inventés.','GenerationAnnuelle.jsx; CampagnesGeneration.jsx')

chapter('8. Exploitation EDT et interopérabilité QR','Après publication seulement, contrôler les vues de la grille, les exports et l’effet sur les séances de Présences. Les écrans masqués du menu restent joignables directement selon droits; ne pas affirmer une opération de mutation sans l’avoir exercée.')
case('Grille et filtres LMD','Ouvrir /edt; filtrer année, filière, formation, niveau, groupe, semestre, semaine, statut; comparer avec campagne.','Seules séances du périmètre filtré sont rendues; aucun S1 dans S2 par défaut.','Edts.jsx')
case('Détail et semaine','Sélectionner un EDT brouillon puis changer semaine; comparer affectations, salles et enseignants.','Détail et grille portent la semaine sélectionnée; effectifs non masqués.','Edts.jsx; edts/urls.py')
case('Détection de conflits','Sur EDT de recette, lancer Détecter les conflits puis consulter /edt/conflits.','Nombre, motifs et séances concernés concordent; aucune résolution silencieuse.','Edts.jsx; edts/services.py')
case('Déplacement de séance','Sur brouillon et compte habilité, déplacer une séance vers un créneau libre, puis tenter vers créneau occupé.','Revalidation des contraintes; état final et éventuels avertissements retracés.','Edts.jsx; edts/urls.py')
case('Annulation motivée et réactivation','Annuler une séance de recette avec motif puis réactiver selon parcours autorisé; relire audit et grille.','Motif conservé; transitions et conflits reflètent l’état réel; EDT publié non modifié directement.','Edts.jsx; edts/urls.py')
case('Export CSV, PDF, XLSX','Sur EDT sélectionné et semaine connue, télécharger chaque format proposé depuis la grille; comparer lignes et totaux.','Fichiers non vides, filtre/année/semaine corrects; aucun hors périmètre.','Edts.jsx; edts/urls.py')
case('Séance publiée vers Présences','Publier un EDT de recette; consulter /presences/seances et l’API d’interop des séances publiées.','Seules séances publiées admissibles exposées; rattachement groupe/date/salle cohérent.','edts/api_interop.py; edts/urls.py; SeancesRegistre.jsx')
case('Brouillon non exposé au QR','Comparer même séance avant et après publication; tenter lecture depuis poste/flux mobile autorisé.','Brouillon non traité comme séance publiée; aucun badgeage associé à une séance non publiée.','edts/api_interop.py; qr_badge_mobile/',profile='Sécurité / Présences')
case('Droits, déconnexion et données personnelles','Avec un compte étudiant/enseignant autorisé, consulter son EDT; changer de compte et tester un périmètre étranger.','Visibilité conforme aux droits serveur; aucun matricule/jeton divulgué dans traces ou captures.','edts/api.py; edts/permissions.py',profile='Lecteur / sécurité')

chapter('9. Contrôles transversaux et clôture','L’objectif est la preuve de conformité sur une version et un périmètre donnés. Les tests automatiques existants aident à diagnostiquer mais ne remplacent ni la recette authentifiée ni l’approbation pédagogique.')
case('Audit des données et contraintes','Ouvrir /edt/audit, sélectionner année; confronter erreurs, contraintes souples/dures et référentiels.','Audit explicite; anomalies non présentées comme conformes.','AuditDonnees.jsx; api_lmd.py')
case('Accès référentiels et erreurs API','Simuler sur environnement isolé 401, 403, 409 et 5xx des API de lecture/génération.','Messages compréhensibles; aucune donnée de démonstration substituée à un échec API.','api_getinjs.py; GenerationAnnuelle.jsx')
case('Régression multi-années','Exécuter lecture et aperçu sur deux années distinctes avec données différentes.','Aucune contamination d’année, de groupe, de compteur ou de campagne.','api_getinjs.py; edts/moteur/annee.py')
case('Reproductibilité et charges','Relever volume réel (groupes, étudiants, créneaux), durée, erreurs, requêtes et version; exécuter benchmark uniquement sur base isolée.','Indicateurs chiffrés et reproductibles, aucun seuil déclaré atteint sans mesure.','edts/management/commands/benchmark_getinjs.py; compteur_sql_getinjs.py')
case('Validation finale de la campagne','Réconcilier rapport d’import, effectifs, dimensionnement, besoins S1/S2, grilles, exports, conflits, versions et Présences; compléter PV.','Aucun GO si un scénario critique échoue ou si preuve/signature manque; réserves et décisions explicites.','Ensemble du module',profile='Direction / responsable de recette',evidence='PV daté et signé selon procédure INJS + références des preuves expurgées.')

assert len(CHAPTERS)==9 and len({x['id'] for c in CHAPTERS for x in c['cases']})==sum(len(c['cases']) for c in CHAPTERS)
N=sum(len(c['cases']) for c in CHAPTERS)
TITLE='MANUEL DÉMO DE RECETTE DE BOUT EN BOUT — GET INJS APP'
PREFACE=[
('Objet','Protocole de test de bout en bout du module de gestion des emplois du temps LMD INJS2026. Ce document décrit des scénarios à exécuter, pas des résultats déjà observés. Les cas couvrent les familles de comportements repérables dans le dépôt et des variantes de risque; « tous les scénarios possibles » au sens mathématique ne peut être garanti par un inventaire fini. Compléter au fil des évolutions.'),
('Périmètre technique','Interface de gestion : React dans frontend/src/pages/getinjs et Edts.jsx ; backend : Django REST sous /api/edts/ (alias /api/timetable/). Flutter qr_badge_mobile concerne le badgeage et la consultation/interop Présences, non l’écran web de génération. Aucun accès à l’application authentifiée ou à la production n’a été utilisé pour établir des résultats.'),
('Mode d’emploi','Pour chaque GET-xxx : choisir jeu de recette isolé, version/commit, année, profil réellement autorisé; exécuter dans l’ordre; comparer le résultat constaté au critère; consigner ÉCHEC / BLOQUÉ / NON APPLICABLE / RÉUSSI seulement après essai, avec ticket et preuve. Une route ou un test unitaire existant ne valide jamais à lui seul le cas métier.'),
('Risques bloquants','Calendrier institutionnel multi-semestre non garanti; ne pas déclarer une année complète si S1/S2 et leurs dates/semaines ne sont pas validés. L’API du tableau de bord peut échouer même si /api/health/ répond. La génération et les écritures sont réservées à un environnement autorisé; ne pas peupler ou réinitialiser la production pour une démo.'),
('Preuves et confidentialité','Conserver captures expurgées, rapports, identifiants de campagnes/EDT, exports anonymisés et traces HTTP sans jetons ni données personnelles. Les pièces restent hors DOCX/PDF dans un répertoire de recette contrôlé. Cases et signatures ci-après sont à renseigner par des personnes habilitées, jamais précochées.'),
]
FLOW=[
('Parcours A — étudiants de la base','Inscriptions administratives validées → population fusionnée GET → référentiels / maquette / salles / enseignants → dimensionnement → aperçu manuel S1 → génération brouillon → audit et correction → validation Direction → publication → grille/export → séances publiées vers Présences. Refaire pour S2 sur semaines officiellement approuvées.'),
('Parcours B — inscrits externes','Modèle CSV/XLSX fictif → analyse sans écriture → import avec rapport des rejets → reconstruction facultative du parcours → groupe/répartition via Scolarité → dimensionnement → génération ciblée ou annuelle si calendrier officiel → campagne, versions et publication sous habilitation → contrôle population/QR.'),
('Arrêt obligatoire','Si année, maquette, ressources, groupe ou calendrier manquent, documenter le blocage et arrêter avant validation/publication; un statut PARTIEL ou IMPOSSIBLE ne vaut pas une homologation d’année.'),
]
RUNBOOK=[
('Fiche de campagne à remplir avant de commencer','Identifiant de recette et ticket de changement : ______ ; URL de l’environnement isolé : ______ ; version backend/frontend/mobile et commit : ______ ; année académique : ______ ; calendrier S1/S2 approuvé par : ______ ; date et plage de semaines autorisées : ______ ; testeur, rôle et responsable de décision : ______. Ne renseigner aucun mot de passe, jeton ni identité d’étudiant réel.'),
('Jeu minimal reproductible','Préparer un dossier d’inscription L1 validée et un dossier non validé, deux groupes de tailles différentes, une maquette S1/S2 approuvée avec UE/ECUE CM, TD, TP, deux enseignants (dont un indisponible), deux salles de capacités différentes et un créneau concurrent. Ajouter un fichier de test fictif avec lignes valide, rejetée et doublon; noter les identifiants et les effectifs dans le référentiel de preuves, pas dans un exemple de production.'),
('Séquence de contrôle avant écriture','1. Relever l’état initial (effectifs, groupes, EDT, séances, versions, conflits, historique). 2. Vérifier année et calendrier officiellement approuvés. 3. Définir à l’avance les comptes de lecture, planification et validation selon leurs permissions effectives. 4. Faire l’analyse d’import et la simulation de dimensionnement puis l’aperçu de génération. 5. Faire approuver le périmètre avant de déclencher une écriture.'),
('Séquence de contrôle après écriture','1. Relever campagne, exécution, HTTP, horodatage et motif d’échec éventuel. 2. Réconcilier effectifs Base/Import, groupes, séances attendues/placées/non placées et heures S1/S2. 3. Détecter conflits, comparer grille et exports. 4. Vérifier la validation/pub uniquement avec la Direction et la propagation aux séances Présences. 5. Conserver preuves expurgées et écart/ticket; ne jamais retoucher les résultats pour obtenir un taux artificiel.'),
('Seuil de sortie','GO possible uniquement après exécution effective des cas applicables, absence d’échec critique sécurité / calendrier / S1-S2 / conflits / publication, preuves consultables et PV signé par les responsables. PARTIEL, IMPOSSIBLE, blocage, cas non exécuté ou absence de calendrier : NO-GO ou décision formelle ajournée. Un test automatique ancien ne remplace pas ce visa.'),
('Journal de chaque cas','GET-xxx | date/heure | environnement et versions | année | profil | jeu de données anonymisé | actions réalisées | HTTP/ID campagne ou EDT | attendu | observé | statut | preuve externe | ticket | testeur | validateur. Le présent document laisse tous les constats vides.'),
]
SOURCES=['frontend/src/menu/arborescence.js, frontend/src/App.jsx','frontend/src/pages/getinjs/{GetInjsApp,GenerationAnnuelle,ImportEtudiants,Dimensionnement,EtudiantsInscrits,Referentiels,CampagnesGeneration,VersionsPublication,AuditDonnees,Conception}.jsx','frontend/src/pages/Edts.jsx, frontend/src/pages/EdtPresences.jsx','backend/edts/{urls.py,permissions.py,api_getinjs.py,api_lmd.py,api_interop.py}','backend/edts/moteur/{annee.py,import_inscrits.py,dimensionnement.py,campagnes.py,besoins.py,besoins_maquette.py}','backend/edts/tests/test_{generation_annee,import_inscrits,dimensionnement,campagnes,interop_presences}.py','docs/getinjs/Conception-GET-INJS.txt (source technique à confronter au code courant)']

# DOCX
navy=RGBColor(18,48,84);blue=RGBColor(35,92,140)
d=Document();sec=d.sections[0];sec.top_margin=Cm(2);sec.bottom_margin=Cm(1.8);sec.left_margin=Cm(2.1);sec.right_margin=Cm(2.1)
styles=d.styles;styles['Normal'].font.name='Calibri';styles['Normal'].font.size=Pt(10)
for s,size in [('Title',22),('Heading 1',16),('Heading 2',12)]:styles[s].font.name='Calibri';styles[s].font.size=Pt(size);styles[s].font.color.rgb=navy
p=d.add_paragraph(style='Title');p.alignment=WD_ALIGN_PARAGRAPH.CENTER;p.add_run(TITLE)
p=d.add_paragraph('INJS • édition documentaire de recette 2026 • version initiale non exécutée');p.alignment=WD_ALIGN_PARAGRAPH.CENTER
p=d.add_paragraph(f'{N} scénarios numérotés | 9 chapitres | DOCX et PDF issus de la même source');p.alignment=WD_ALIGN_PARAGRAPH.CENTER
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
footer=sec.footer.paragraphs[0];footer.alignment=WD_ALIGN_PARAGRAPH.CENTER;footer.text='GET INJS APP • protocole de recette — non exécuté • INJS2026'
OUT.mkdir(parents=True,exist_ok=True);d.save(OUT/f'{BASE}.docx')

# PDF, même structure et mêmes champs (sans utiliser Word/LibreOffice).
pdfmetrics.registerFont(TTFont('DejaVu','/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'))
pdfmetrics.registerFont(TTFont('DejaVuBold','/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'))
ss=getSampleStyleSheet();ss.add(ParagraphStyle(name='GTTitle',fontName='DejaVuBold',fontSize=17,leading=24,textColor=HexColor('#123054'),spaceAfter=16,alignment=TA_CENTER));ss.add(ParagraphStyle(name='GT1',fontName='DejaVuBold',fontSize=13,leading=18,textColor=HexColor('#123054'),spaceBefore=15,spaceAfter=7));ss.add(ParagraphStyle(name='GT2',fontName='DejaVuBold',fontSize=10,leading=15,textColor=HexColor('#235c8c'),spaceBefore=9,spaceAfter=5));ss.add(ParagraphStyle(name='GTBody',fontName='DejaVu',fontSize=8.6,leading=13,spaceAfter=5));ss.add(ParagraphStyle(name='GTSmall',fontName='DejaVu',fontSize=7.7,leading=11,spaceAfter=7));ss.add(ParagraphStyle(name='GTWarn',fontName='DejaVuBold',fontSize=8.7,leading=13,textColor=HexColor('#9c3027'),spaceAfter=10))
def pp(text,sty='GTBody'):return Paragraph(escape(text).replace('\n','<br/>'),ss[sty])
def labelled(l,v):return Paragraph(f'<b>{escape(l)} :</b> {escape(v)}',ss['GTBody'])
story=[pp(TITLE,'GTTitle'),pp('INJS • édition documentaire de recette 2026 • version initiale non exécutée'),pp(f'{N} scénarios numérotés | 9 chapitres | DOCX et PDF issus de la même source'),pp('STATUT : PROTOCOLE À EXÉCUTER — AUCUNE VALIDATION MÉTIER PRÉREMPLIE','GTWarn')]
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
 canvas.saveState();canvas.setFont('DejaVu',8);canvas.setFillColor(HexColor('#5c7086'));canvas.drawString(42,27,'GET INJS APP • protocole non exécuté');canvas.drawRightString(A4[0]-42,27,f'Page {doc.page}');canvas.restoreState()
SimpleDocTemplate(str(OUT/f'{BASE}.pdf'),pagesize=A4,rightMargin=43,leftMargin=43,topMargin=42,bottomMargin=48,title=TITLE,author='INJS • protocole de recette').build(story,onFirstPage=decoration,onLaterPages=decoration)
print('Créés',N,'cas',len(CHAPTERS),'chapitres',OUT)
