"""Peuplement des charges pédagogiques INJS pour une année académique.

Contexte
--------
L'écran « Charges pédagogiques des enseignants » (Scolarité) était vide :
aucune maquette ACTIVE pour l'année courante (la charge « prévue » en
dérive), aucun volume sur les ECUE, 2 enseignants seulement et zéro
``AffectationPedagogique``. Cette commande — de démonstration, données
fictives étiquetées — construit la chaîne complète, dans l'ordre imposé
par les règles métier (une maquette VALIDEE/ACTIVE est immuable) :

1. crée les maquettes ``[Exemple]`` des filières sans référentiel publié
   (F05–F08) en BROUILLON, via le créateur de ``finaliser_maquettes_injs`` ;
2. renseigne les volumes CM/TD/TP des ECUE encore à 0, par une grille
   **MODELISE** déduite des intitulés (document « Modéliser les volumes
   horaires au niveau Formation → Catégorie → Module » du dossier INJS :
   UE de 25 à 70 h, stages encadrés) — jamais après validation ;
3. délègue validation + activation à ``finaliser_maquettes_injs``
   (crédits ventilés, cohérence vérifiée, transitions journalisées) ;
4. crée autant d'enseignants fictifs que nécessaire (fiche Formateur
   complète : badge, grade du référentiel enseignants, fonction, statut,
   spécialité, contacts — compte bancaire volontairement non inventé),
   spécialisés par école et domaine, sans dépasser le seuil de surcharge
   (paramètre ``volume_horaire_max_enseignant``, défaut 192 h/an) ;
5. affecte chaque ECUE des maquettes ACTIVE de l'année à un enseignant
   (une affectation VALIDEE par ECUE, type = composante dominante
   CM/TD/TP, volume = volume total de l'ECUE, dates du semestre).

Idempotente : enseignants ``demo.ens.*`` / badges ``ENS-DEMO-*`` réutilisés,
affectations retrouvées par (année, ECUE, type), volumes déjà renseignés
ou maquettes verrouillées jamais réécrits.

Exemples
--------
    python manage.py peupler_charges_pedagogiques_injs --dry-run
    python manage.py peupler_charges_pedagogiques_injs
    python manage.py peupler_charges_pedagogiques_injs --annee 2026-2027
"""
import re
import unicodedata
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from formations.models import Formateur
from referentiels.models import RefGradeEnseignant
from scolarite.charges_services import _seuil_surcharge
from scolarite.models import (
    AffectationPedagogique, AnneeAcademique, ECUE, Maquette,
)

User = get_user_model()

MARQUE = '[Démo fictive]'
PREFIXE_BADGE = 'ENS-DEMO-'
PREFIXE_USERNAME = 'demo.ens.'
MOT_DE_PASSE_DEMO = 'DemoInjs2026!'
#: En deçà du seuil de surcharge, on préfère créer un nouvel enseignant.
CIBLE_CREATION = 170

ECOLE_PAR_FILIERE = {
    'F01': 'ENSEPS', 'F02': 'ENSEPS', 'F03': 'ENSEPS', 'F04': 'ENSEPS',
    'F05': 'ENSEP', 'F06': 'ENSEP', 'F07': 'ENSEP', 'F08': 'ENSEP',
}
SIGLE_PAR_FILIERE = {
    'F01': 'EM', 'F02': 'APA', 'F03': 'ES', 'F04': 'MS',
    'F05': 'AND', 'F06': 'LOI', 'F07': 'EJCP', 'F08': 'GER',
}
DOMAINE_PAR_SIGLE_ENSEP = {
    'AND': 'Andragogie et éducation permanente',
    'LOI': 'Loisir et animation socioculturelle',
    'EJCP': 'Entrepreneuriat jeunesse et conduite de projets',
    'GER': 'Gérontologie et intervention sociale',
}

# Grades enseignants (codes du référentiel GRADES ET STATUTS INJS), pondérés.
GRADES_ROTATION = [
    'MAITRE_ASSISTANT', 'MAITRE_EPS', 'ASSISTANT', 'MAITRE_CONFERENCES',
    'MAITRE_ASSISTANT', 'PROF_AGREGE_EPS', 'MAITRE_ASSISTANT', 'ASSISTANT',
    'MAITRE_CONFERENCES', 'PROFESSEUR_TITULAIRE',
]
GRADES_TITULAIRES = {
    'PROFESSEUR_TITULAIRE', 'MAITRE_CONFERENCES', 'MAITRE_ASSISTANT',
    'PROF_AGREGE_EPS', 'MAITRE_EPS',
}

PRENOMS = [
    'Aya', 'Koffi', 'Mariam', 'Jean-Marc', 'Fatou', 'Yao', 'Aïcha', 'Kouadio',
    'Nadia', 'Serge', 'Larissa', 'Ibrahim', 'Aminata', 'Olivier', 'Marie',
    'Fatima', 'Jean-Bosco', 'Souleymane', 'Emmanuelle', 'Konan', 'Adjoua',
    'Moussa', 'Reine', 'Patrick', 'Sandrine', 'Bakary', 'Christelle', 'Daouda',
    'Estelle', 'Thierry', 'Valérie', 'Hamadou', 'Laure', 'Guy', 'Inès',
]
NOMS_FAMILLE = [
    'Kouadio', 'N’Guessan', 'Touré', 'Aka', 'Sangaré', 'Koné', 'Bamba',
    'Coulibaly', 'Diabaté', 'Diarra', 'Traoré', 'Ouattara', 'Fofana', 'Camara',
    'Diallo', 'Barry', 'Sow', 'Bah', 'Kourouma', 'Keïta', 'Dembélé', 'Sissoko',
    'Yao', 'N’Dri', 'Ehui', 'Gba', 'Kouamé', 'Yoboué', 'Zadi', 'Goné',
    'Tano', 'Brou', 'Achi', 'Miézan', 'Kassi', 'Diby',
]

# ── Volumes MODELISE (heures CM/TD/TP par ECUE) ─────────────────────────────
# Grilles du document « Modéliser les volumes horaires » ramenées à
# l'échelle d'une ECUE (les UE du document totalisent 25 à 70 h pour
# 2 à 5 ECUE). Ordre des règles : la première qui correspond s'applique.
REGLES_VOLUMES = [
    (r'stage|mémoire|insertion professionnelle|pratique professionnelle',
     (0, 5, 25)),
    (r'initiation aux fondamentaux|spécialisation|football|handball|basketball|'
     r'volleyball|rugby|athlétisme|gymnastique|natation|judo|boxe|escrime|'
     r'tennis|cyclisme|haltérophilie|arts martiaux|sports? (collectifs?|de combat|individuels?)|'
     r'danse|pratique(s)? (sportive|physique|de l)',
     (4, 6, 20)),
    (r'didactique|pédagogie|enseignement|intervention|encadrement|animation',
     (10, 10, 10)),
    (r'anatomie|physiologie|biomécanique|biochimie|santé|pathologie|nutrition|'
     r'secourisme|médical|handicap|motricité|psychomotricité|ergonomie|'
     r'rééducation|réadaptation|kiné|exercice|motrice|fonctionnelle',
     (12, 8, 6)),
    (r'psychologie|sociologie|histoire|philosophie|anthropologie|communication|'
     r'anglais|français|langue|études|milieu|environnement',
     (10, 8, 0)),
    (r'management|gestion|droit|économ|marketing|entrepreneur|finance|comptab|'
     r'informatique|tic|technolog|statistique|recherche|méthodologie|'
     r'épistémologie|évaluation|ingénierie|projet|andragogie|gérontologie|'
     r'loisir|éducation|formation',
     (10, 8, 4)),
]
VOLUME_DEFAUT = (8, 6, 4)

# ── Domaines de spécialité (rattachement des enseignants) ───────────────────
REGLES_DOMAINES = [
    (r'anatomie|physiologie|biomécanique|biochimie|santé|pathologie|nutrition|'
     r'secourisme|médical|handicap|motricité|psychomotricité|ergonomie|'
     r'rééducation|réadaptation|exercice|motrice|fonctionnelle',
     'Sciences de la vie et de la santé'),
    (r'psychologie|sociologie|histoire|philosophie|anthropologie|sciences humaines',
     'Sciences humaines et sociales'),
    (r'football|handball|basketball|volleyball|rugby|sports? collectifs?',
     'APS — sports collectifs'),
    (r'athlétisme|gymnastique|natation|judo|boxe|escrime|tennis|cyclisme|'
     r'haltérophilie|arts martiaux|sports? (de combat|individuels?)|danse|'
     r'initiation aux fondamentaux|spécialisation|pratique',
     'APS — sports individuels et pratiques physiques'),
    (r'didactique|pédagogie|enseignement|intervention|encadrement|éducation|formation',
     'Didactique, pédagogie et intervention'),
    (r'management|gestion|droit|économ|marketing|entrepreneur|finance|comptab|projet',
     'Management, gestion et droit du sport'),
]
DOMAINE_TRANSVERSAL = 'Recherche, langues et TIC'
REGLES_TRANSVERSAL = (
    r'recherche|méthodologie|statistique|épistémologie|anglais|français|'
    r'communication|informatique|tic|technolog|évaluation'
)


def _norm(texte):
    return unicodedata.normalize('NFKD', texte or '').encode(
        'ascii', 'ignore').decode().lower()


def volumes_pour_ecue(intitule):
    """(CM, TD, TP) MODELISE déterministes d'après l'intitulé de l'ECUE."""
    texte = _norm(intitule)
    for motif, volumes in REGLES_VOLUMES:
        if re.search(motif, texte):
            return volumes
    return VOLUME_DEFAUT


def domaine_pour(intitule, sigle):
    """Spécialité d'enseignement déduite de l'intitulé (défaut : transversal)."""
    texte = _norm(intitule)
    if re.search(REGLES_TRANSVERSAL, texte):
        return DOMAINE_TRANSVERSAL
    for motif, domaine in REGLES_DOMAINES:
        if re.search(motif, texte):
            return domaine
    if sigle in DOMAINE_PAR_SIGLE_ENSEP:
        return DOMAINE_PAR_SIGLE_ENSEP[sigle]
    return DOMAINE_TRANSVERSAL


def _type_dominant(cm, td, tp):
    if tp >= cm and tp >= td:
        return AffectationPedagogique.TypeEnseignement.TP
    if td >= cm:
        return AffectationPedagogique.TypeEnseignement.TD
    return AffectationPedagogique.TypeEnseignement.CM


class Command(BaseCommand):
    help = (
        'Peuple les charges pédagogiques INJS d\'une année : volumes ECUE '
        'MODELISE, maquettes validées/activées (via finaliser), enseignants '
        'fictifs complets et une affectation VALIDEE par ECUE.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--annee', help="Libellé d'année (défaut : année courante).")
        parser.add_argument('--utilisateur', help='Signataire des transitions de maquettes.')
        parser.add_argument('--sans-exemples', action='store_true',
                            help='Ne pas créer les maquettes [Exemple] F05–F08.')
        parser.add_argument('--dry-run', action='store_true', help='Simuler sans écrire.')

    # ── Enseignants ──────────────────────────────────────────────────────
    def _prochain_identite(self, seq):
        prenom = PRENOMS[seq % len(PRENOMS)]
        nom = NOMS_FAMILLE[(seq // len(PRENOMS)) % len(NOMS_FAMILLE)]
        return prenom, nom

    def _creer_enseignant(self, seq, ecole, domaine):
        prenom, nom = self._prochain_identite(seq)
        username = f'{PREFIXE_USERNAME}{seq:03d}'
        badge = f'{PREFIXE_BADGE}{seq:03d}'
        user, _ = User.objects.get_or_create(
            username=username,
            defaults={'role': User.Role.FORMATEUR,
                      'first_name': prenom, 'last_name': nom,
                      'email': f'{username}@demo.injs.ci'},
        )
        if not user.check_password(MOT_DE_PASSE_DEMO):
            user.set_password(MOT_DE_PASSE_DEMO)
            user.save(update_fields=['password'])
        # profile_sync crée déjà un Formateur lié au compte FORMATEUR.
        formateur = Formateur.objects.filter(user=user).first()
        if formateur is None:
            formateur = Formateur(user=user, numerobadge=badge)
        grade_code = GRADES_ROTATION[seq % len(GRADES_ROTATION)]
        grade_ref = RefGradeEnseignant.objects.filter(code=grade_code).first()
        formateur.numerobadge = badge
        formateur.nom = nom
        formateur.prenom = prenom
        formateur.email = f'{_norm(prenom)}.{_norm(nom).replace(" ", "")}@demo.injs.ci'
        formateur.telephone = f'+225 07 08 {seq:02d} {10 + seq % 80} {10 + (seq * 7) % 80}'
        formateur.specialite = domaine
        formateur.organisation = ecole
        formateur.grade_ref = grade_ref
        formateur.statut_enseignant = (
            'Titulaire' if grade_code in GRADES_TITULAIRES and seq % 5 != 4
            else 'Vacataire'
        )
        formateur.numero_piece_identite = f'DEMO-CI-{seq:04d}'
        # numero_compte_bancaire volontairement vide : aucun numéro inventé.
        formateur.observations = (
            f'{MARQUE} Enseignant fictif créé pour les charges pédagogiques '
            f'{ecole} — volumes et affectations MODELISE.'
        )
        formateur.save()
        return formateur

    # ── Étapes ───────────────────────────────────────────────────────────
    def _remplir_volumes(self, annee):
        """Volumes MODELISE sur les ECUE à 0 des maquettes non verrouillées."""
        modifies = 0
        maquettes = Maquette.objects.filter(
            annee_academique=annee, statut=Maquette.Statut.BROUILLON)
        for maquette in maquettes:
            for ecue in ECUE.objects.filter(ue__maquette=maquette):
                if float(ecue.volume_total) > 0:
                    continue
                cm, td, tp = volumes_pour_ecue(ecue.intitule)
                ecue.volume_cm = Decimal(cm)
                ecue.volume_td = Decimal(td)
                ecue.volume_tp = Decimal(tp)
                ecue.save(update_fields=['volume_cm', 'volume_td', 'volume_tp'])
                modifies += 1
        return modifies

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        with transaction.atomic():
            bilan = self._peupler(options)
            if dry_run:
                transaction.set_rollback(True)
                self.stdout.write(self.style.WARNING('Simulation (dry-run) : rien n\'a été écrit.'))
        for cle, valeur in bilan.items():
            self.stdout.write(f'  {cle} : {valeur}')
        self.stdout.write(self.style.SUCCESS('Charges pédagogiques INJS peuplées.'))

    def _peupler(self, options):
        if options.get('annee'):
            annee = AnneeAcademique.objects.filter(libelle=options['annee']).first()
        else:
            annee = AnneeAcademique.objects.filter(courante=True).first()
        if annee is None:
            raise CommandError('Aucune année académique cible (courante ou --annee).')

        bilan = {'annee': annee.libelle}

        # 1) Maquettes [Exemple] F05–F08 en BROUILLON (créateur officiel).
        if not options['sans_exemples']:
            from scolarite.management.commands.finaliser_maquettes_injs import (
                Command as FinaliserCommand,
            )
            finaliser = FinaliserCommand()
            finaliser.stdout = self.stdout
            finaliser.style = self.style
            bilan['maquettes_exemples_creees'] = finaliser._creer_exemples(annee, False)

        # 2) Volumes MODELISE avant toute validation (maquette ensuite immuable).
        bilan['ecue_volumes_remplies'] = self._remplir_volumes(annee)

        # 3) Validation + activation journalisées (commande officielle).
        call_command(
            'finaliser_maquettes_injs', annee=annee.libelle,
            utilisateur=options.get('utilisateur'), sans_exemples=True,
            verbosity=0,
        )
        maquettes_actives = list(
            Maquette.objects.filter(annee_academique=annee, statut=Maquette.Statut.ACTIVE)
            .select_related('ref_formation', 'niveau', 'parcours'))
        bilan['maquettes_actives'] = len(maquettes_actives)
        bilan['maquettes_non_activees'] = Maquette.objects.filter(
            annee_academique=annee).exclude(statut=Maquette.Statut.ACTIVE).count()

        # 4) Enseignants : pools (école, domaine), charges suivies en mémoire.
        seuil = float(_seuil_surcharge())
        cible = min(CIBLE_CREATION, seuil)
        pools = {}
        charges = {}
        seq_max = 0
        for formateur in Formateur.objects.filter(
                numerobadge__startswith=PREFIXE_BADGE).select_related('user'):
            try:
                seq = int(formateur.numerobadge.replace(PREFIXE_BADGE, ''))
            except ValueError:
                continue
            seq_max = max(seq_max, seq)
            pools.setdefault((formateur.organisation, formateur.specialite), []).append(formateur)
        for aff in AffectationPedagogique.objects.filter(annee_academique=annee).exclude(
                statut=AffectationPedagogique.Statut.ANNULEE):
            charges[aff.enseignant_id] = charges.get(aff.enseignant_id, 0.0) + float(aff.volume_horaire)

        def enseignant_pour(ecole, domaine, volume):
            nonlocal seq_max
            candidats = pools.setdefault((ecole, domaine), [])
            disponibles = [f for f in candidats if charges.get(f.id, 0.0) + volume <= cible]
            if not disponibles:
                if candidats and min(charges.get(f.id, 0.0) for f in candidats) + volume <= seuil:
                    disponibles = candidats
                else:
                    seq_max += 1
                    nouveau = self._creer_enseignant(seq_max, ecole, domaine)
                    candidats.append(nouveau)
                    bilan['enseignants_crees'] = bilan.get('enseignants_crees', 0) + 1
                    return nouveau
            return min(disponibles, key=lambda f: charges.get(f.id, 0.0))

        # 5) Une affectation VALIDEE par ECUE des maquettes ACTIVE.
        milieu = annee.date_debut + (annee.date_fin - annee.date_debut) / 2
        crees = existantes = 0
        volume_total = 0.0
        ecues = (
            ECUE.objects.filter(ue__maquette__in=maquettes_actives)
            .select_related('ue__semestre', 'ue__maquette__ref_formation',
                            'ue__maquette__niveau', 'ue__maquette__parcours')
            .order_by('ue__maquette__ref_formation__intitule', 'ue__maquette__niveau__ordre',
                      'ue__semestre__numero', 'ue__ordre', 'ordre')
        )
        for ecue in ecues:
            maquette = ecue.ue.maquette
            formation = maquette.ref_formation
            sigle = SIGLE_PAR_FILIERE.get(formation.filiere_code, '')
            ecole = ECOLE_PAR_FILIERE.get(formation.filiere_code, 'ENSEPS')
            domaine = domaine_pour(f'{ecue.ue.intitule} {ecue.intitule}', sigle)
            volume = float(ecue.volume_total)
            type_ens = _type_dominant(float(ecue.volume_cm), float(ecue.volume_td), float(ecue.volume_tp))
            # Idempotence stricte : une ECUE déjà affectée ne déclenche
            # aucune sélection (sinon un pool saturé créerait un enseignant
            # inutile à chaque nouvelle passe).
            if AffectationPedagogique.objects.filter(
                    annee_academique=annee, ecue=ecue, type_enseignement=type_ens
            ).exclude(statut=AffectationPedagogique.Statut.ANNULEE).exists():
                existantes += 1
                volume_total += volume
                continue
            enseignant = enseignant_pour(ecole, domaine, volume)
            semestre = ecue.ue.semestre
            if semestre.numero % 2 == 1:
                debut, fin = annee.date_debut, milieu
            else:
                debut, fin = milieu + timedelta(days=1), annee.date_fin
            _, cree = AffectationPedagogique.objects.get_or_create(
                annee_academique=annee, ecue=ecue, type_enseignement=type_ens,
                defaults={
                    'ref_formation': formation, 'parcours': maquette.parcours,
                    'niveau': maquette.niveau, 'semestre': semestre,
                    'ue': ecue.ue, 'enseignant': enseignant,
                    'volume_horaire': Decimal(str(volume)),
                    'date_debut': debut, 'date_fin': fin,
                    'statut': AffectationPedagogique.Statut.VALIDEE,
                    'observations': (
                        f'{MARQUE} Charge générée depuis la maquette '
                        f'{formation.intitule} {maquette.niveau.code} — volume MODELISE.'
                    ),
                },
            )
            if cree:
                crees += 1
                charges[enseignant.id] = charges.get(enseignant.id, 0.0) + volume
            else:
                existantes += 1
            volume_total += volume

        bilan['ecue_couvertes'] = crees + existantes
        bilan['affectations_creees'] = crees
        bilan['affectations_existantes'] = existantes
        bilan['volume_total_affecte_h'] = round(volume_total, 2)
        bilan['enseignants_total'] = Formateur.objects.filter(
            numerobadge__startswith=PREFIXE_BADGE).count()
        bilan['charge_max_h'] = round(max(charges.values()), 2) if charges else 0
        bilan['seuil_surcharge_h'] = seuil
        return bilan
