"""API du lot L5 — Stages et conventions.

Pattern @api_view (cohérent avec graduation/jurys/equivalences).
"""
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import ConventionStage, EvaluationStage, OrganismeAccueil, TuteurExterne
from .permissions import IsSecretariatOrEncadrant, IsSecretariatOrEncadrantOrReadOnly
from . import services


def _serialize_organisme(o):
    return {
        'id': o.id, 'nom': o.nom, 'raison_sociale': o.raison_sociale,
        'adresse': o.adresse, 'ville': o.ville, 'pays': o.pays,
        'contact_nom': o.contact_nom, 'contact_telephone': o.contact_telephone,
        'contact_email': o.contact_email, 'actif': o.actif,
    }


def _serialize_tuteur(t):
    return {
        'id': t.id, 'organisme_id': t.organisme_id,
        'organisme_nom': t.organisme.nom,
        'nom': t.nom, 'prenom': t.prenom, 'fonction': t.fonction,
        'email': t.email, 'telephone': t.telephone, 'actif': t.actif,
    }


def _serialize_evaluation(e):
    return {
        'id': e.id, 'convention_id': e.convention_id,
        'note_aptitude': float(e.note_aptitude) if e.note_aptitude is not None else None,
        'note_integration': float(e.note_integration) if e.note_integration is not None else None,
        'note_autonomie': float(e.note_autonomie) if e.note_autonomie is not None else None,
        'note_production': float(e.note_production) if e.note_production is not None else None,
        'note_rapport': float(e.note_rapport) if e.note_rapport is not None else None,
        'appreciation_libre': e.appreciation_libre,
        'note_finale': float(e.note_finale) if e.note_finale is not None else None,
        'mention': e.mention, 'mention_display': e.get_mention_display(),
        'evalue_par': str(e.evalue_par) if e.evalue_par_id else None,
        'valide_par': str(e.valide_par) if e.valide_par_id else None,
        'date_evaluation': e.date_evaluation.isoformat(),
        'date_validation': e.date_validation.isoformat() if e.date_validation else None,
    }


def _serialize_convention(c):
    return {
        'id': c.id,
        'etudiant_id': c.etudiant_id,
        'etudiant_nom_complet': c.etudiant.nom_complet,
        'etudiant_matricule': c.etudiant.matricule,
        'annee_academique_id': c.annee_academique_id,
        'annee_academique': str(c.annee_academique),
        'ref_formation_id': c.ref_formation_id,
        'ref_formation': str(c.ref_formation) if c.ref_formation_id else None,
        'organisme_id': c.organisme_id,
        'organisme_nom': c.organisme.nom,
        'tuteur_externe_id': c.tuteur_externe_id,
        'tuteur_externe': str(c.tuteur_externe) if c.tuteur_externe_id else None,
        'encadrant_interne_id': c.encadrant_interne_id,
        'intitule': c.intitule,
        'sujet': c.sujet[:200],
        'date_debut': c.date_debut.isoformat(),
        'date_fin': c.date_fin.isoformat(),
        'lieu': c.lieu,
        'statut': c.statut,
        'statut_display': c.get_statut_display(),
        'motif_refus': c.motif_refus,
        'date_soumission': c.date_soumission.isoformat() if c.date_soumission else None,
        'date_validation_admin': c.date_validation_admin.isoformat() if c.date_validation_admin else None,
        'valide_par': str(c.valide_par) if c.valide_par_id else None,
        'date_signature': c.date_signature.isoformat() if c.date_signature else None,
        'note_rapport': float(c.note_rapport) if c.note_rapport is not None else None,
        'note_soutenance': float(c.note_soutenance) if c.note_soutenance is not None else None,
        'mention': c.mention,
        'rapport_url': c.rapport_fichier.url if c.rapport_fichier else None,
        'convention_pdf_url': c.convention_pdf.url if c.convention_pdf else None,
        'date_archivage': c.date_archivage.isoformat() if c.date_archivage else None,
        'commentaires': c.commentaires,
        'audit_evaluation': (_serialize_evaluation(c.evaluation) if hasattr(c, 'evaluation') else None),
    }


# ---------- Organismes ----------

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def organismes_list_api(request):
    qs = OrganismeAccueil.objects.all().order_by('nom')
    actif = request.GET.get('actif')
    if actif in ('true', 'false'):
        qs = qs.filter(actif=actif == 'true')
    return Response({'results': [_serialize_organisme(o) for o in qs]})


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrEncadrantOrReadOnly])
def organisme_creer_api(request):
    for ch in ('nom',):
        if not request.data.get(ch):
            return Response({'error': f"Champ obligatoire manquant : {ch}."}, status=400)
    try:
        o = OrganismeAccueil.objects.create(
            nom=request.data['nom'],
            raison_sociale=request.data.get('raison_sociale', ''),
            adresse=request.data.get('adresse', ''),
            ville=request.data.get('ville', ''),
            pays=request.data.get('pays', "Côte d'Ivoire"),
            contact_nom=request.data.get('contact_nom', ''),
            contact_telephone=request.data.get('contact_telephone', ''),
            contact_email=request.data.get('contact_email', ''),
        )
    except Exception as exc:
        return Response({'error': str(exc)}, status=400)
    return Response(_serialize_organisme(o), status=201)


@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated, IsSecretariatOrEncadrantOrReadOnly])
def organisme_detail_api(request, pk):
    try:
        o = OrganismeAccueil.objects.get(pk=pk)
    except OrganismeAccueil.DoesNotExist:
        return Response({'error': "Organisme introuvable."}, status=404)
    if request.method == 'GET':
        return Response(_serialize_organisme(o))
    for champ in ('nom', 'raison_sociale', 'adresse', 'ville', 'pays', 'contact_nom',
                  'contact_telephone', 'contact_email', 'actif'):
        if champ in request.data:
            setattr(o, champ, request.data[champ])
    o.save()
    return Response(_serialize_organisme(o))


# ---------- Tuteurs ----------

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def tuteurs_list_api(request):
    qs = TuteurExterne.objects.select_related('organisme').all()
    organisme_id = request.GET.get('organisme_id')
    if organisme_id:
        qs = qs.filter(organisme_id=organisme_id)
    return Response({'results': [_serialize_tuteur(t) for t in qs]})


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrEncadrantOrReadOnly])
def tuteur_creer_api(request):
    for ch in ('organisme_id', 'nom'):
        if not request.data.get(ch):
            return Response({'error': f"Champ obligatoire manquant : {ch}."}, status=400)
    try:
        organisme = OrganismeAccueil.objects.get(pk=request.data['organisme_id'])
    except OrganismeAccueil.DoesNotExist:
        return Response({'error': "Organisme introuvable."}, status=404)
    try:
        t = TuteurExterne.objects.create(
            organisme=organisme, nom=request.data['nom'],
            prenom=request.data.get('prenom', ''),
            fonction=request.data.get('fonction', ''),
            email=request.data.get('email', ''),
            telephone=request.data.get('telephone', ''),
        )
    except Exception as exc:
        return Response({'error': str(exc)}, status=400)
    return Response(_serialize_tuteur(t), status=201)


# ---------- Conventions ----------

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def conventions_list_api(request):
    qs = ConventionStage.objects.select_related(
        'etudiant__participant', 'annee_academique', 'ref_formation',
        'organisme', 'tuteur_externe', 'valide_par',
    ).order_by('-created_at')
    statut = request.GET.get('statut')
    if statut:
        qs = qs.filter(statut=statut)
    etudiant_id = request.GET.get('etudiant_id')
    if etudiant_id:
        qs = qs.filter(etudiant_id=etudiant_id)
    annee_id = request.GET.get('annee_academique_id')
    if annee_id:
        qs = qs.filter(annee_academique_id=annee_id)
    return Response({'results': [_serialize_convention(c) for c in qs]})


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrEncadrantOrReadOnly])
def convention_creer_api(request):
    from scolarite.models import AnneeAcademique, DossierEtudiant
    for ch in ('etudiant_id', 'annee_academique_id', 'organisme_id', 'intitule',
               'sujet', 'date_debut', 'date_fin'):
        if not request.data.get(ch):
            return Response({'error': f"Champ obligatoire manquant : {ch}."}, status=400)
    try:
        etudiant = DossierEtudiant.objects.get(pk=request.data['etudiant_id'])
        annee = AnneeAcademique.objects.get(pk=request.data['annee_academique_id'])
        organisme = OrganismeAccueil.objects.get(pk=request.data['organisme_id'])
    except (DossierEtudiant.DoesNotExist, AnneeAcademique.DoesNotExist,
            OrganismeAccueil.DoesNotExist) as exc:
        return Response({'error': str(exc)}, status=400)
    try:
        c = ConventionStage.objects.create(
            etudiant=etudiant, annee_academique=annee, organisme=organisme,
            ref_formation_id=request.data.get('ref_formation_id') or None,
            tuteur_externe_id=request.data.get('tuteur_externe_id') or None,
            encadrant_interne_id=request.data.get('encadrant_interne_id') or None,
            intitule=request.data['intitule'],
            sujet=request.data['sujet'],
            objectifs=request.data.get('objectifs', ''),
            date_debut=request.data['date_debut'],
            date_fin=request.data['date_fin'],
            lieu=request.data.get('lieu', ''),
            cree_par=request.user,
        )
    except Exception as exc:
        return Response({'error': str(exc)}, status=400)
    return Response(_serialize_convention(c), status=201)


@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated, IsSecretariatOrEncadrantOrReadOnly])
def convention_detail_api(request, pk):
    try:
        c = ConventionStage.objects.get(pk=pk)
    except ConventionStage.DoesNotExist:
        return Response({'error': "Convention introuvable."}, status=404)
    if request.method == 'GET':
        return Response(_serialize_convention(c))
    if c.statut != ConventionStage.Statut.BROUILLON:
        return Response(
            {'error': f"Convention {c.statut} non éditable — utilisez /transition/."},
            status=400,
        )
    for champ in ('intitule', 'sujet', 'objectifs', 'date_debut', 'date_fin', 'lieu',
                  'organisme_id', 'tuteur_externe_id', 'encadrant_interne_id',
                  'ref_formation_id', 'commentaires'):
        if champ in request.data:
            setattr(c, champ, request.data[champ])
    c.save()
    return Response(_serialize_convention(c))




@api_view(['POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrEncadrant])
def convention_transition_api(request, pk):
    """Transition contrôlée par machine à états."""
    try:
        c = ConventionStage.objects.get(pk=pk)
    except ConventionStage.DoesNotExist:
        return Response({'error': "Convention introuvable."}, status=404)
    cible = request.data.get('statut') or request.data.get('cible')
    motif = request.data.get('motif_refus', '')
    try:
        services.appliquer_transition(c, cible, request.user, motif_refus=motif)
    except Exception as exc:
        return Response({'error': str(exc)}, status=400)
    c.refresh_from_db()
    return Response(_serialize_convention(c))


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def convention_pdf_api(request, pk):
    """Téléchargement du PDF signé de la convention."""
    from django.http import HttpResponse
    try:
        c = ConventionStage.objects.get(pk=pk)
    except ConventionStage.DoesNotExist:
        return Response({'error': "Convention introuvable."}, status=404)
    if not c.convention_pdf:
        return Response({'error': "Aucun PDF de convention disponible."}, status=404)
    with c.convention_pdf.open('rb') as f:
        contenu = f.read()
    reponse = HttpResponse(contenu, content_type='application/pdf')
    reponse['Content-Disposition'] = f'attachment; filename="convention-{c.pk}.pdf"'
    return reponse


# ---------- Évaluations ----------

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def evaluations_list_api(request):
    qs = EvaluationStage.objects.select_related('convention').all()
    return Response({'results': [_serialize_evaluation(e) for e in qs]})


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrEncadrant])
def evaluation_creer_api(request, convention_id):
    """Crée ou met à jour l'évaluation d'une convention (valider pour VALIDEE_JURY)."""
    try:
        c = ConventionStage.objects.get(pk=convention_id)
    except ConventionStage.DoesNotExist:
        return Response({'error': "Convention introuvable."}, status=404)
    try:
        e = services.enregistrer_evaluation(
            c,
            note_aptitude=request.data.get('note_aptitude'),
            note_integration=request.data.get('note_integration'),
            note_autonomie=request.data.get('note_autonomie'),
            note_production=request.data.get('note_production'),
            note_rapport=request.data.get('note_rapport'),
            appreciation_libre=request.data.get('appreciation_libre', ''),
            user=request.user,
            valider=bool(request.data.get('valider', False)),
        )
    except Exception as exc:
        return Response({'error': str(exc)}, status=400)
    return Response(_serialize_evaluation(e), status=201)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def evaluation_detail_api(request, pk):
    try:
        e = EvaluationStage.objects.select_related('convention').get(pk=pk)
    except EvaluationStage.DoesNotExist:
        return Response({'error': "Évaluation introuvable."}, status=404)
    return Response(_serialize_evaluation(e))

