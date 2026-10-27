from django.contrib import admin

from .models import (
    AffectationGroupe,
    AnneeAcademique,
    EvenementScolarite,
    DossierEtudiant,
    ECUE,
    Groupe,
    InscriptionAdministrative,
    InscriptionPedagogique,
    JournalScolarite,
    Maquette,
    Niveau,
    Parcours,
    RegimeEtudes,
    Semestre,
    StatutEtudiant,
    TypeFormation,
    UE,
)


@admin.register(AnneeAcademique)
class AnneeAcademiqueAdmin(admin.ModelAdmin):
    list_display = ('libelle', 'date_debut', 'date_fin', 'courante', 'actif')
    list_filter = ('courante', 'actif')
    search_fields = ('libelle',)


@admin.register(TypeFormation)
class TypeFormationAdmin(admin.ModelAdmin):
    list_display = ('code', 'libelle', 'actif')
    list_filter = ('actif',)
    search_fields = ('code', 'libelle')


@admin.register(Niveau)
class NiveauAdmin(admin.ModelAdmin):
    list_display = ('code', 'libelle', 'cycle', 'ordre', 'credits_requis', 'actif')
    list_filter = ('cycle', 'actif')
    search_fields = ('code', 'libelle')


@admin.register(Semestre)
class SemestreAdmin(admin.ModelAdmin):
    list_display = ('libelle', 'niveau', 'numero', 'actif')
    list_filter = ('niveau', 'actif')


@admin.register(Parcours)
class ParcoursAdmin(admin.ModelAdmin):
    list_display = ('code', 'intitule', 'ref_formation', 'type_formation', 'actif')
    list_filter = ('actif', 'type_formation')
    search_fields = ('code', 'intitule')
    autocomplete_fields = ('ref_formation',)


@admin.register(RegimeEtudes)
class RegimeEtudesAdmin(admin.ModelAdmin):
    list_display = ('code', 'libelle', 'actif')
    list_filter = ('actif',)


@admin.register(StatutEtudiant)
class StatutEtudiantAdmin(admin.ModelAdmin):
    list_display = ('code', 'libelle', 'bloque_inscription', 'actif')
    list_filter = ('actif', 'bloque_inscription')


@admin.register(Groupe)
class GroupeAdmin(admin.ModelAdmin):
    list_display = ('nom', 'annee_academique', 'ref_formation', 'niveau', 'vague', 'capacite_max', 'actif')
    list_filter = ('annee_academique', 'niveau', 'actif')
    search_fields = ('nom',)


class ECUEInline(admin.TabularInline):
    model = ECUE
    extra = 0


@admin.register(UE)
class UEAdmin(admin.ModelAdmin):
    list_display = ('code', 'intitule', 'maquette', 'semestre', 'credits', 'caractere')
    list_filter = ('caractere', 'semestre')
    search_fields = ('code', 'intitule')
    inlines = [ECUEInline]


class UEInline(admin.TabularInline):
    model = UE
    extra = 0
    show_change_link = True


@admin.register(Maquette)
class MaquetteAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'annee_academique', 'ref_formation', 'niveau', 'version', 'statut')
    list_filter = ('statut', 'annee_academique', 'niveau')
    inlines = [UEInline]


@admin.register(ECUE)
class ECUEAdmin(admin.ModelAdmin):
    list_display = ('code', 'intitule', 'ue', 'credits', 'volume_total', 'ref_module')
    search_fields = ('code', 'intitule')


class InscriptionInline(admin.TabularInline):
    model = InscriptionAdministrative
    extra = 0
    show_change_link = True
    fields = ('annee_academique', 'ref_formation', 'niveau', 'type_inscription', 'statut')
    readonly_fields = ('date_validation', 'valide_par')


@admin.register(DossierEtudiant)
class DossierEtudiantAdmin(admin.ModelAdmin):
    list_display = ('matricule', 'nom_complet', 'statut', 'date_premiere_inscription')
    list_filter = ('statut',)
    search_fields = (
        'participant__matricule', 'participant__nom', 'participant__prenom',
    )
    readonly_fields = ('uuid',)
    inlines = [InscriptionInline]


@admin.register(InscriptionAdministrative)
class InscriptionAdministrativeAdmin(admin.ModelAdmin):
    list_display = (
        'etudiant', 'annee_academique', 'ref_formation', 'niveau',
        'type_inscription', 'statut', 'date_inscription',
    )
    list_filter = ('statut', 'type_inscription', 'annee_academique', 'niveau')
    search_fields = (
        'etudiant__participant__matricule',
        'etudiant__participant__nom',
        'etudiant__participant__prenom',
    )
    readonly_fields = ('date_validation', 'valide_par')


@admin.register(AffectationGroupe)
class AffectationGroupeAdmin(admin.ModelAdmin):
    list_display = ('inscription', 'groupe', 'date_debut', 'date_fin', 'active')
    list_filter = ('active', 'groupe__niveau')
    search_fields = ('inscription__etudiant__participant__matricule', 'groupe__nom')


@admin.register(EvenementScolarite)
class EvenementScolariteAdmin(admin.ModelAdmin):
    list_display = (
        'date_evenement', 'etudiant', 'type_evenement', 'ancienne_valeur', 'nouvelle_valeur',
    )
    list_filter = ('type_evenement',)
    search_fields = (
        'etudiant__participant__matricule',
        'etudiant__participant__nom',
        'commentaire',
    )


@admin.register(InscriptionPedagogique)
class InscriptionPedagogiqueAdmin(admin.ModelAdmin):
    list_display = (
        'inscription', 'ecue', 'semestre', 'groupe',
        'type_enseignement', 'credits', 'statut', 'origine',
    )
    list_filter = ('statut', 'origine', 'type_enseignement', 'semestre')
    search_fields = (
        'ecue__code', 'ecue__intitule',
        'inscription__etudiant__participant__matricule',
    )


@admin.register(JournalScolarite)
class JournalScolariteAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'action', 'objet_libelle', 'acteur_label', 'nouvelle_valeur')
    list_filter = ('action',)
    search_fields = ('objet_libelle', 'acteur_label', 'commentaire')
    readonly_fields = [f.name for f in JournalScolarite._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
