"""Génère la trame de recette NON exécutée des dix espaces retenus (openpyxl)."""
from pathlib import Path
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.formatting.rule import CellIsRule
from openpyxl.utils import get_column_letter
from openpyxl.workbook.properties import CalcProperties

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'dossier_trvx/Manuel_jeu_test2026/Recette_Validation_10_Hubs_INJS_2026.xlsx'
# Périmètre proposé : huit composants *Hub.jsx + deux espaces transversaux.
# Les routes sont des points d'entrée de recette, pas des attestations de fonctionnement.
HUBS = {
 'Tableau de bord': ('DashboardEngineView.jsx', [('/dashboard','Vue d’ensemble'),('/dashboard','Scolarité'),('/dashboard','Pédagogie'),('/dashboard','Finances'),('/dashboard','Jurys'),('/dashboard','Présences'),('/dashboard','Administration'),('/dashboard','Vue Étudiant'),('/dashboard','Vue Enseignant')]),
 'Scolarité': ('ScolariteDashboard.jsx / arborescence.js', [('/scolarite','Tableau de bord'),('/scolarite/candidatures','Candidatures'),('/scolarite','Contrôle des dossiers (menu sans route App.jsx)'),('/scolarite/campagnes','Concours et sélection'),('/scolarite','Résultats concours (menu sans route App.jsx)'),('/scolarite/admissions','Admissions'),('/scolarite/inscriptions','Inscriptions'),('/participants','Étudiants'),('/scolarite/groupes','Groupes pédagogiques'),('/scolarite/documents-scolaires','Documents scolaires'),('/scolarite/maquettes','Maquettes LMD'),('/scolarite/equivalences','Équivalences et dispenses'),('/scolarite/reinscriptions','Réinscriptions et transferts'),('/scolarite/journal','Journal de scolarité')]),
 'Présences QR': ('PresencesHub.jsx / arborescence.js', [('/presences','Supervision'),('/presences/seances','Séances'),('/presences/poste','Badgeage'),('/presences/registre','Registre'),('/presences/audit','Audit'),('/presences/configuration','Configuration géofence'),('/presences/contrat','Contrat API')]),
 'Évaluations': ('EvaluationsHub.jsx', [('/evaluations/saisie','Saisie des notes'),('/evaluations/controle','Contrôle et validation'),('/evaluations/releves','Relevés'),('/evaluations/saisie','Sessions'),('/evaluations/saisie','Évaluations'),('/evaluations/saisie','Types d’évaluation')]),
 'Jurys': ('JurysHub.jsx', [('/jurys/validation','Sessions'),('/jurys/composition','Composition'),('/jurys/deliberations','Décisions et délibérations'),('/jurys/pv','PV et publications')]),
 'Diplômation': ('DiplomationHub.jsx', [('/diplomation/eligibilite','Éligibilité'),('/diplomation/attestations','Diplômes et attestations'),('/diplomation/certificats','Certificats et gabarits'),('/diplomation/registres','Registres et modèles')]),
 'Finances étudiantes': ('FinancesHub.jsx', [('/finances-etudiantes/frais','Frais et barème'),('/finances-etudiantes/factures','Factures'),('/finances-etudiantes/paiements','Paiements'),('/finances-etudiantes/recus','Reçus et quittances'),('/finances-etudiantes/bourses','Bourses et remboursements'),('/finances-etudiantes/situation','Situation financière'),('/finances-etudiantes/situation','Échéanciers'),('/finances-etudiantes/situation','Relances et rapprochements')]),
 'Stages': ('StagesHub.jsx', [('/stages/conventions','Conventions'),('/stages/organismes','Structures d’accueil'),('/stages/affectations','Affectations et tuteurs'),('/stages/suivi','Suivi'),('/stages/evaluations','Évaluations')]),
 'Personnel': ('PersonnelHub.jsx', [('/personnel/agents','Agents'),('/personnel/affectations','Affectations'),('/personnel/disponibilites','Disponibilités'),('/personnel/documents','Documents RH'),('/personnel/fonctions','Fonctions'),('/personnel/services','Services')]),
 'Administration': ('AdministrationHub.jsx', [('/administration/courrier','Courrier'),('/administration/courrier','Documents officiels'),('/administration/reunions','Réunions et commissions'),('/administration/reunions','Missions'),('/organisation','Directions (menu sans route App.jsx)'),('/organisation','Départements (menu sans route App.jsx)'),('/organisation','Services (menu sans route App.jsx)')]),
}
# Les sous-onglets sans route propre restent associés à leur route parente ; navigation à vérifier.
EXTRAS = [
 ('Tableau de bord','Vue d’ensemble','Panne API métier','Sur une session de recette, rendre l’API de synthèse indisponible dans un environnement isolé; ouvrir la vue.','Une erreur explicite apparaît, aucun chiffre n’est substitué; noter HTTP et contexte.'),
 ('Scolarité','Inscriptions','Contrôle S1/S2','Avec un dossier de recette autorisé, vérifier inscription S1 puis S2 et réouvrir le dossier.','Les deux semestres sont distincts et cohérents; aucune validation implicite.'),
 ('Présences QR','Badgeage','QR invalide ou expiré','Soumettre un QR invalide/expiré sur une séance de recette isolée.','Refus explicite; aucune présence créée; relever l’événement d’audit.'),
 ('Présences QR','Badgeage','Double badgeage','Soumettre deux fois le même badgeage sur une séance de recette isolée.','Aucune double présence; documenter les réponses et le registre.'),
 ('Présences QR','Configuration géofence','Hors périmètre','Tester un badgeage hors zone sur un site de recette configuré.','Refus ou exception tracée selon la règle appliquée; aucune validation silencieuse.'),
 ('Évaluations','Contrôle et validation','Droit de validation','Avec un compte sans droit de validation, tenter la validation d’une note de recette.','Action refusée; la note ne devient pas validée.'),
 ('Jurys','Décisions et délibérations','Décision non publiée','Préparer une décision de recette sans publication puis consulter avec un profil non autorisé.','Aucune décision non publiée divulguée.'),
 ('Diplômation','Éligibilité','Dossier incomplet','Contrôler un dossier de recette incomplet avant toute émission de document.','Le motif d’inéligibilité est traçable; aucun document délivré indûment.'),
 ('Finances étudiantes','Paiements','Paiement sans preuve','Dans l’environnement de recette, vérifier le refus ou l’état en attente d’un paiement sans justificatif requis.','Aucun reçu final non justifié; conserver la réponse observée.'),
 ('Stages','Conventions','Convention non signée','Tester la suite du parcours d’une convention non signée avec dossier de recette.','Statut cohérent; aucune signature présumée ou inventée.'),
 ('Personnel','Documents RH','Accès non autorisé','Tenter l’accès au document de recette depuis un compte sans habilitation RH.','Aucune donnée du document exposée; consigner HTTP et écran.'),
 ('Administration','Courrier','Courrier sans habilitation','Tenter la consultation d’un courrier de recette avec un compte non habilité.','Accès refusé sans divulgation du contenu.'),
]
NAV = {h: {f:r for r,f in feats} for h,(_,feats) in HUBS.items()}
wb=Workbook(); guide=wb.active; guide.title='Mode d’emploi'; tests=wb.create_sheet('Cas de recette'); dashboard=wb.create_sheet('Progression'); bil=wb.create_sheet('Bilan par Hub')
wb.calculation=CalcProperties(calcMode='auto', fullCalcOnLoad=True)
navy='17365D'; pale='E7F0FA'; gold='FCE8B2'; white='FFFFFF'; green='E4F3E8'

def title(ws, text, end):
 ws.merge_cells(start_row=1,start_column=1,end_row=1,end_column=end)
 c=ws.cell(1,1,text);c.fill=PatternFill('solid',fgColor=navy);c.font=Font(name='Aptos',size=16,bold=True,color=white);c.alignment=Alignment(vertical='center');ws.row_dimensions[1].height=34

def header(ws,row,labels):
 for i,v in enumerate(labels,1):
  c=ws.cell(row,i,v);c.fill=PatternFill('solid',fgColor=navy);c.font=Font(color=white,bold=True);c.alignment=Alignment(wrap_text=True,vertical='center')
 ws.row_dimensions[row].height=36

def widths(ws, spec):
 for col,width in spec.items():ws.column_dimensions[col].width=width

def dv_list(ws,col,items,start,end):
 dv=DataValidation(type='list',formula1='"'+','.join(items)+'"',allow_blank=False);dv.showErrorMessage=True;dv.errorTitle='Valeur non autorisée';dv.error='Choisir une valeur de la liste.';dv.errorStyle='stop';ws.add_data_validation(dv);dv.add(f'{col}{start}:{col}{end}')

title(guide,'RECETTE INJS • protocole de validation',6)
notes=[
 'Trame non exécutée : aucune fonctionnalité n’est déclarée fonctionnelle. Les routes et sous-onglets servent seulement de points de départ; vérifier leur présence et les droits en situation.',
 'Périmètre de dix espaces de travail PROPOSÉ : 8 composants explicitement nommés *Hub.jsx, plus Tableau de bord et Scolarité. Cette liste n’est pas attestée comme la nomenclature institutionnelle officielle : faire valider le périmètre avant signature.',
 'Tester sur environnement isolé et comptes autorisés, jamais sur des données personnelles ou en production sans autorisation. Noter l’environnement, la version et le profil effectivement utilisé.',
 'Cas de recette : une ligne = une fonctionnalité et un scénario. Filtrer par Hub; exécuter les étapes; saisir résultat observé, date, testeur, statut, et chemin/URL de preuve dans le stockage officiel. Ne jamais insérer un secret dans le classeur.',
 'Statuts : Non exécuté (initial), Réussi, Échec, Bloqué, Non applicable. Un succès ne compte comme preuve complète que si date, testeur, environnement, résultat observé et référence de preuve sont renseignés.',
 'Une preuve est une référence à une pièce conservée hors classeur (capture expurgée, export anonymisé, journal expurgé ou ticket); joindre la pièce selon la procédure interne. Un chemin écrit seul ne garantit pas son existence : vérification humaine obligatoire.',
 'Non applicable : préciser justification et décision du responsable dans résultat observé + preuve et testeur/date; il ne vaut JAMAIS un succès et empêche la validation automatique à 100 %.',
 'Progression calcule automatiquement les succès documentés et les dossiers incomplets. Le bilan par Hub n’est recevable que si tous les cas sont réussis avec preuve, décision explicite Validé, signataire, date et référence de PV saisis.',
 'Les cellules vertes à saisir sont distinctes des formules bleues : ne pas effacer ni remplacer les formules. Excel ou LibreOffice doit recalculer les formules à l’ouverture. La signature doit être réalisée selon la procédure institutionnelle hors du simple nom dans une cellule.',
 'Cinq entrées de menu n’ont pas de route déclarée dans App.jsx (contrôle des dossiers, résultats concours, directions, départements, services) : point d’entrée parent indiqué; enregistrer Bloqué/Non applicable si la fonction est introuvable.',
 'Si un cas est incompatible avec la version déployée, noter Bloqué/Non applicable et faire arbitrer le périmètre; ne pas transformer une absence de test en Réussi.',
 'Sources : frontend/src/App.jsx, frontend/src/menu/arborescence.js, frontend/src/pages/*/*Hub.jsx, DashboardEngineView.jsx, ScolariteDashboard.jsx. Inventaire de code ≠ test métier.',
]
for r,text in enumerate(notes,3):guide.merge_cells(start_row=r,start_column=1,end_row=r,end_column=6);c=guide.cell(r,1,text);c.alignment=Alignment(wrap_text=True,vertical='center');c.fill=PatternFill('solid',fgColor=pale if r%2 else white);guide.row_dimensions[r].height=43 if len(text)>190 else 32
widths(guide,{'A':25,'B':25,'C':25,'D':25,'E':25,'F':25});guide.freeze_panes='A3'
headers=['ID','Hub','Fonctionnalité','Cas / objectif','Point d’entrée','Source code / menu','Prérequis / profil','Étapes à exécuter','Résultat attendu','Statut','Date exécution','Testeur','Environnement / version','Résultat observé / anomalie','Référence preuve à joindre','Ticket / réserve','Contrôle automatique']
title(tests,'CAS DE RECETTE • résultats à saisir uniquement après exécution',17);header(tests,3,headers)
rows=[]
for hi,(hub,(source,features)) in enumerate(HUBS.items(),1):
 for fi,(route,feature) in enumerate(features,1):
  rows.append((f'H{hi:02d}-F{fi:02d}-C01',hub,feature,'Accès et consultation',route,source,'Compte habilité, jeu de recette identifié',f'Ouvrir {route}; sélectionner « {feature} » si onglet; relever chargement, valeurs et erreurs.', 'L’écran ou l’onglet charge les données autorisées sans erreur; valeurs confrontées au jeu de recette.'))
  rows.append((f'H{hi:02d}-F{fi:02d}-C02',hub,feature,'Filtre / recherche / détail',route,source,'Compte habilité, au moins un enregistrement de recette',f'Dans « {feature} », appliquer un filtre ou une recherche si disponible; ouvrir un détail si proposé; comparer avec le jeu de recette.', 'Les résultats correspondent aux critères; si l’action n’existe pas, noter Bloqué/Non applicable avec justification, jamais Réussi.'))
for ix,(hub,feature,case,steps,expected) in enumerate(EXTRAS,1):
 rows.append((f'X{ix:03d}',hub,feature,case,NAV[hub][feature],HUBS[hub][0],'Compte(s) et données de recette isolées; habilitations à vérifier',steps,expected))
for r,vals in enumerate(rows,4):
 for col,v in enumerate(vals,1):tests.cell(r,col,v)
 tests.cell(r,10,'Non exécuté')
 tests.cell(r,17,f'=IF(J{r}="Réussi",IF(AND(ISNUMBER(K{r}),L{r}<>"",M{r}<>"",N{r}<>"",O{r}<>""),"Succès documenté","Succès incomplet"),IF(J{r}="Non exécuté","Non exécuté",IF(AND(ISNUMBER(K{r}),L{r}<>"",N{r}<>""),"À arbitrer","Dossier incomplet")))')
 for c in range(1,18):
  cell=tests.cell(r,c);cell.alignment=Alignment(vertical='top',wrap_text=c in (3,4,7,8,9,14,15,16,17));cell.fill=PatternFill('solid',fgColor=green if 10<=c<=16 else (white if r%2==0 else 'F3F7FB'))
 tests.cell(r,11).number_format='dd/mm/yyyy';tests.row_dimensions[r].height=44
last=3+len(rows);tests.auto_filter.ref=f'A3:Q{last}';tests.freeze_panes='D4';tests.sheet_view.zoomScale=80
widths(tests,dict(zip('ABCDEFGHIJKLMNOPQ',[20,22,27,29,29,33,38,70,65,19,18,22,28,65,52,35,24])))
dv_list(tests,'J',['Non exécuté','Réussi','Échec','Bloqué','Non applicable'],4,last)
dateval=DataValidation(type='date',operator='between',formula1='DATE(2020,1,1)',formula2='DATE(2100,12,31)',allow_blank=True);dateval.showErrorMessage=True;dateval.error='Saisir une date valide.';tests.add_data_validation(dateval);dateval.add(f'K4:K{last}')
for text,color in [('Succès documenté','C6EFCE'),('Succès incomplet','FFEB9C'),('Dossier incomplet','FFC7CE')]:
 tests.conditional_formatting.add(f'Q4:Q{last}',CellIsRule(operator='equal',formula=['"'+text+'"'],fill=PatternFill('solid',fgColor=color)))

title(dashboard,'PROGRESSION • aucun résultat présumé',10)
header(dashboard,3,['Hub','Cas prévus','Succès documentés','Succès incomplets','Échecs','Bloqués','Non applicables','Non exécutés','Progression prouvée','À arbitrer / incomplets'])
for r,hub in enumerate(HUBS,4):
 dashboard.cell(r,1,hub)
 dashboard.cell(r,2,f'=COUNTIF(\'Cas de recette\'!$B$4:$B${last},A{r})')
 for c,label in [(3,'Succès documenté'),(4,'Succès incomplet'),(5,'Échec'),(6,'Bloqué'),(7,'Non applicable'),(8,'Non exécuté')]:
  dashboard.cell(r,c,f'=COUNTIFS(\'Cas de recette\'!$B$4:$B${last},A{r},\'Cas de recette\'!$Q$4:$Q${last},"{label}")' if c<5 or c==8 else f'=COUNTIFS(\'Cas de recette\'!$B$4:$B${last},A{r},\'Cas de recette\'!$J$4:$J${last},"{label}")')
 dashboard.cell(r,9,f'=IFERROR(C{r}/B{r},0)').number_format='0.0%'
 dashboard.cell(r,10,f'=B{r}-C{r}-H{r}')
 dashboard.cell(r,1).hyperlink=f"#'Bilan par Hub'!A{r}"
r=14;dashboard.cell(r,1,'TOTAL');
for col in range(2,9):letter=get_column_letter(col);dashboard.cell(r,col,f'=SUM({letter}4:{letter}13)')
dashboard.cell(r,9,'=IFERROR(C14/B14,0)').number_format='0.0%';dashboard.cell(r,10,'=B14-C14-H14')
dashboard.cell(16,1,'La progression correspond uniquement aux succès réellement consignés avec preuve et identité du testeur. Une ligne « Réussi » incomplète ne progresse pas.');dashboard.merge_cells('A16:J16');dashboard.cell(16,1).alignment=Alignment(wrap_text=True);dashboard.row_dimensions[16].height=36
widths(dashboard,{'A':27,**{get_column_letter(i):22 for i in range(2,11)}});dashboard.freeze_panes='B4';dashboard.auto_filter.ref='A3:J13'

title(bil,'BILAN • visa individuel pour chaque Hub',12)
header(bil,3,['Hub','Cas prévus','Succès avec preuve','Reste à valider','Taux prouvé','Décision du responsable','Nom et fonction du signataire','Date de visa','Référence du PV signé','Réserves / commentaires','Recevabilité calculée','Source / périmètre'])
for r,(hub,(source,_)) in enumerate(HUBS.items(),4):
 bil.cell(r,1,hub)
 for col,dc in [(2,'B'),(3,'C'),(4,'J'),(5,'I')]:bil.cell(r,col,f'=Progression!{dc}{r}')
 bil.cell(r,5).number_format='0.0%';bil.cell(r,8).number_format='dd/mm/yyyy';bil.cell(r,12,source)
 bil.cell(r,11,f'=IF(AND(B{r}>0,C{r}=B{r},D{r}=0,F{r}="Validé",G{r}<>"",ISNUMBER(H{r}),I{r}<>""),"Visa recevable*","Non validé")')
 for col in range(6,11):bil.cell(r,col).fill=PatternFill('solid',fgColor=green);bil.cell(r,col).alignment=Alignment(wrap_text=True,vertical='center')
 bil.row_dimensions[r].height=42
bil.merge_cells('A16:L16');bil.cell(16,1,'* Recevabilité formelle seulement : vérifier humainement les pièces, les identités, la cohérence des résultats et le PV signé hors classeur.');bil.cell(16,1).alignment=Alignment(wrap_text=True);bil.row_dimensions[16].height=34
bil.merge_cells('A17:L17');bil.cell(17,1,'Aucun Hub n’est validé à la livraison. Une décision manuelle « Validé » ne suffit jamais si la recette n’est pas complète et documentée.');bil.cell(17,1).alignment=Alignment(wrap_text=True);bil.row_dimensions[17].height=34
widths(bil,dict(zip('ABCDEFGHIJKL',[25,16,20,20,16,22,33,18,35,44,23,36])))
dv_list(bil,'F',['En attente','Validé','Refusé','Validé avec réserves'],4,13)
bil.freeze_panes='B4';bil.auto_filter.ref='A3:L13'
for ws in wb:
 ws.sheet_properties.pageSetUpPr.fitToPage=True
 ws.page_setup.fitToWidth=1
 ws.sheet_properties.outlinePr.summaryBelow=True
# Une régénération ne doit jamais écraser une recette déjà renseignée ou signée.
if OUT.exists():
 raise SystemExit(f"Refus d'écraser le classeur existant : {OUT}")
OUT.parent.mkdir(parents=True,exist_ok=True);wb.save(OUT)
print(OUT, 'hubs=',len(HUBS),'cases=',len(rows),'bytes=',OUT.stat().st_size)
