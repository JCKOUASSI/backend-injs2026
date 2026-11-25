from django import forms
from django.core.exceptions import ValidationError

from apps.referentiels.models import Module, TypeFormation

from .models import (
    Batiment,
    Grade,
    JourFerie,
    ModuleTypeFormation,
    PARAMETRES_PLANIFICATION_FIELD_NAMES,
    ParametreFormation,
    ParametreGeneral,
    PeriodeDisponibiliteSite,
    Salle,
    Site,
    Vague,
)


class TypeFormationForm(forms.ModelForm):
    """Formulaire de création / modification d'un type de formation."""

    class Meta:
        model = TypeFormation
        fields = ["code", "libelle"]
        widgets = {
            "code": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ex: FAC"}),
            "libelle": forms.TextInput(attrs={"class": "form-control", "placeholder": "Libellé complet"}),
        }


JOURS_CHOICES = [
    (0, "Lundi"),
    (1, "Mardi"),
    (2, "Mercredi"),
    (3, "Jeudi"),
    (4, "Vendredi"),
    (5, "Samedi"),
    (6, "Dimanche"),
]


class GradeForm(forms.ModelForm):
    """Formulaire d'ajout / modification d'un grade."""

    class Meta:
        model = Grade
        fields = ["libelle"]
        widgets = {
            "libelle": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Ex: A3, A4, B3, C3...",
                    "title": "Libellé du grade (ex: A3, A4, B3, B4, C3, C4, D3)",
                }
            ),
        }


class VagueForm(forms.ModelForm):
    """Formulaire d'ajout / modification d'une vague."""

    class Meta:
        model = Vague
        fields = ["libelle"]
        widgets = {
            "libelle": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ex: 2025-A"}),
        }


class SiteForm(forms.ModelForm):
    """Formulaire d'ajout d'un site."""

    class Meta:
        model = Site
        fields = ["nom"]
        widgets = {
            "nom": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ex: Site Plateau"}),
        }


class PeriodeDisponibiliteSiteForm(forms.ModelForm):
    """Formulaire d'ajout / modification d'une période de disponibilité d'un site."""

    class Meta:
        model = PeriodeDisponibiliteSite
        fields = ["site", "date_debut", "date_fin"]
        widgets = {
            "site": forms.Select(attrs={"class": "form-select"}),
            "date_debut": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "date_fin": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["site"].queryset = Site.objects.filter(actif=True).order_by("nom")
        self.fields["site"].required = True


class BatimentForm(forms.ModelForm):
    """Formulaire d'ajout d'un bâtiment."""

    class Meta:
        model = Batiment
        fields = ["site", "nom"]
        widgets = {
            "site": forms.Select(attrs={"class": "form-select"}),
            "nom": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ex: Bâtiment A"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["site"].queryset = Site.objects.filter(actif=True).order_by("nom")
        self.fields["site"].required = True

    def clean_site(self):
        """Empêche l'affectation d'un bâtiment à un site inactif."""
        site = self.cleaned_data.get("site")
        if site is None:
            raise ValidationError("Le site est obligatoire.")
        if not site.actif:
            raise ValidationError("Impossible de créer un bâtiment sur un site inactif.")
        return site


class SalleForm(forms.ModelForm):
    """Formulaire d'ajout d'une salle."""

    class Meta:
        model = Salle
        fields = ["batiment", "nom", "capacite_max"]
        widgets = {
            "batiment": forms.Select(attrs={"class": "form-select"}),
            "nom": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ex: Salle 101"}),
            "capacite_max": forms.NumberInput(attrs={"class": "form-control", "min": 1, "placeholder": "Ex: 30"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["batiment"].queryset = Batiment.objects.filter(actif=True).order_by("nom")
        self.fields["batiment"].required = True
        self.fields["capacite_max"].required = False
        self.fields["capacite_max"].initial = 25

    def clean_batiment(self):
        """Empêche l'affectation d'une salle à un bâtiment inactif."""
        batiment = self.cleaned_data.get("batiment")
        if batiment is None:
            raise ValidationError("Le bâtiment est obligatoire.")
        if not batiment.actif:
            raise ValidationError("Impossible de créer une salle sur un bâtiment inactif.")
        if batiment.site_id and not batiment.site.actif:
            raise ValidationError("Impossible de créer une salle sur un bâtiment rattaché à un site inactif.")
        return batiment


class _ParametresPlanificationFormMixin:
    """Champs et widgets communs aux formulaires de paramètres de planification.

    Note : ``jours_defaut`` est défini dans ``__init__`` plutôt que comme attribut
    de classe car ce mixin n'utilise pas la ``DeclarativeFieldsMetaclass`` ; un
    attribut de classe ne serait donc pas collecté et le ``JSONField`` auto-généré
    par ``ModelForm`` resterait en place (causant des échecs de validation
    silencieux lorsqu'aucun jour n'est coché).
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["jours_defaut"] = forms.MultipleChoiceField(
            choices=JOURS_CHOICES,
            widget=forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
            required=False,
            label="Jours de cours par défaut",
        )
        if self.instance and getattr(self.instance, "jours_defaut", None):
            self.fields["jours_defaut"].initial = self.instance.jours_defaut

    def clean_jours_defaut(self) -> list[int]:
        """Convertit les choix en liste d'entiers."""
        raw = self.cleaned_data.get("jours_defaut", [])
        if raw is None:
            return []
        if not isinstance(raw, (list, tuple)):
            raw = [raw]
        return [int(j) for j in raw]


_PARAMETRES_PLANIFICATION_WIDGETS = {
    "max_auditeurs_groupe_defaut": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
    "groupes_auto_mixage_grades": forms.CheckboxInput(attrs={"class": "form-check-input"}),
    "matin_heure_debut_defaut": forms.TimeInput(attrs={"class": "form-control", "type": "time"}),
    "matin_heure_fin_defaut": forms.TimeInput(attrs={"class": "form-control", "type": "time"}),
    "soir_heure_debut_defaut": forms.TimeInput(attrs={"class": "form-control", "type": "time"}),
    "soir_heure_fin_defaut": forms.TimeInput(attrs={"class": "form-control", "type": "time"}),
    "duree_seance_defaut_minutes": forms.NumberInput(attrs={"class": "form-control", "min": 30}),
    "max_seances_par_jour_defaut": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
    "max_salles_simultanees_module": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
    "tolerance_capacite_salle": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
    "verrouiller_salle_groupe_formation": forms.CheckboxInput(attrs={"class": "form-check-input"}),
    "repartir_reliquat_sur_seances": forms.CheckboxInput(attrs={"class": "form-check-input"}),
    "poids_score_ecart_capacite": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
    "poids_score_rotation_module": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
    "poids_score_equilibrage_global": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
}


class ParametreFormationForm(_ParametresPlanificationFormMixin, forms.ModelForm):
    """Formulaire des paramètres de planification d'une formation."""

    class Meta:
        model = ParametreFormation
        fields = list(PARAMETRES_PLANIFICATION_FIELD_NAMES)
        widgets = _PARAMETRES_PLANIFICATION_WIDGETS


class ParametreGeneralForm(_ParametresPlanificationFormMixin, forms.ModelForm):
    """Formulaire des valeurs par défaut (modèle global + simulation)."""

    class Meta:
        model = ParametreGeneral
        fields = list(PARAMETRES_PLANIFICATION_FIELD_NAMES) + ["marge_simulation_pct"]
        widgets = {
            **_PARAMETRES_PLANIFICATION_WIDGETS,
            "marge_simulation_pct": forms.NumberInput(attrs={"class": "form-control", "min": 0, "max": 100}),
        }


class ModuleForm(forms.ModelForm):
    """Formulaire de création d'un module dans le référentiel global."""

    class Meta:
        model = Module
        fields = ["titre"]
        widgets = {
            "titre": forms.TextInput(attrs={"class": "form-control", "placeholder": "Titre du module"}),
        }


class ModuleTypeFormationForm(forms.ModelForm):
    """Formulaire d'association module ↔ type de formation avec volume horaire par défaut.

    Le champ ``grade_cible`` permet de sélectionner plusieurs grades à la fois
    (une association distincte sera créée pour chaque grade coché). Cocher
    « Tous grades » remplace toute autre sélection et crée une association
    générique (``grade_cible = ""``).
    """

    TOUS_GRADES_SENTINEL = "__ALL__"

    grade_cible = forms.MultipleChoiceField(
        choices=[],
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
        label="Grades concernés",
        help_text="Cochez « Tous grades » ou un ou plusieurs grades spécifiques.",
    )

    class Meta:
        model = ModuleTypeFormation
        fields = ["module", "type_formation", "volume_horaire_defaut"]
        widgets = {
            "module": forms.Select(attrs={"class": "form-select"}),
            "type_formation": forms.Select(attrs={"class": "form-select"}),
            "volume_horaire_defaut": forms.NumberInput(
                attrs={"class": "form-control", "min": 1, "placeholder": "Ex: 20"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["module"].queryset = Module.objects.filter(actif=True).order_by("titre")
        self.fields["type_formation"].queryset = TypeFormation.objects.all().order_by("code")
        grades = list(Grade.objects.filter(actif=True).order_by("ordre", "libelle").values_list("libelle", flat=True))
        self.fields["grade_cible"].choices = [(self.TOUS_GRADES_SENTINEL, "Tous grades")] + [(g, g) for g in grades]

    def clean_grade_cible(self):
        """Renvoie la liste des grades retenus.

        - Aucun choix coché → équivaut à « Tous grades » (liste ``[""]``).
        - « Tous grades » coché → on ignore les autres et on renvoie ``[""]``.
        - Sinon → on renvoie la liste des grades cochés (non vides, normalisés).
        """
        values = self.cleaned_data.get("grade_cible") or []
        if not values or self.TOUS_GRADES_SENTINEL in values:
            return [""]
        grades = []
        seen: set[str] = set()
        for v in values:
            g = (v or "").strip().upper()
            if g and g not in seen:
                seen.add(g)
                grades.append(g)
        return grades or [""]


class JourFerieForm(forms.ModelForm):
    """Formulaire d'ajout d'un jour férié."""

    class Meta:
        model = JourFerie
        fields = ["date", "libelle"]
        widgets = {
            "date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "libelle": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ex: Fête nationale"}),
        }
