from __future__ import annotations

from django import forms

from apps.parametrage.models import Batiment, Grade, Salle, Site
from apps.referentiels.models import Module

from .models import Formation, FormationModule, FormationPeriode


class FormationForm(forms.ModelForm):
    """Formulaire de création / modification d'une formation."""

    rythme_mensuel = forms.MultipleChoiceField(
        choices=Formation.RythmeMensuel.choices,
        required=False,
        widget=forms.CheckboxSelectMultiple(),
        label="Contrainte de rythme mensuel",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.parametrage.repositories import VagueRepository

        vagues = VagueRepository().list_actifs()
        choices = [("", "— Sélectionner une vague —")] + [(v.libelle, v.libelle) for v in vagues]
        self.fields["vague"] = forms.ChoiceField(
            choices=choices,
            required=False,
            widget=forms.Select(attrs={"class": "form-select"}),
            label="Vague",
        )
        if getattr(self.instance, "pk", None):
            self.fields["rythme_mensuel"].initial = [self.instance.rythme_mensuel]
        else:
            self.fields["rythme_mensuel"].initial = [Formation.RythmeMensuel.TOUT_LE_MOIS]

    class Meta:
        model = Formation
        fields = [
            "type_formation",
            "intitule",
            "vague",
            "date_debut",
            "date_fin",
            "rythme_mensuel",
        ]
        widgets = {
            "type_formation": forms.Select(attrs={"class": "form-select"}),
            "intitule": forms.TextInput(attrs={"class": "form-control", "placeholder": "Intitulé de la formation"}),
            "date_debut": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "date_fin": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
        }
        labels = {
            "rythme_mensuel": "Contrainte de rythme mensuel",
        }
        help_texts = {
            "rythme_mensuel": (
                "Valeur par défaut pour les nouvelles périodes. Le rythme effectif au planning "
                "est défini sur chaque période du programme."
            ),
        }

    def clean_rythme_mensuel(self):
        values = [v for v in self.cleaned_data.get("rythme_mensuel", []) if v]
        if not values:
            return Formation.RythmeMensuel.TOUT_LE_MOIS
        if len(values) > 1:
            raise forms.ValidationError("Sélectionnez une seule contrainte de rythme mensuel.")
        return values[0]


class FormationPeriodeForm(forms.Form):
    """Formulaire de création / modification d'une période pédagogique."""

    libelle = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Ex. Trimestre 1"}),
        label="Libellé",
    )
    date_debut = forms.DateField(
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
        label="Date de début",
    )
    date_fin = forms.DateField(
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
        label="Date de fin",
    )
    rythme_mensuel = forms.MultipleChoiceField(
        choices=Formation.RythmeMensuel.choices,
        required=False,
        widget=forms.CheckboxSelectMultiple(),
        label="Contrainte de rythme mensuel",
        help_text="Une seule option : semaines planifiables par mois ou tout le mois.",
    )

    def __init__(self, *args, instance: FormationPeriode | None = None, formation: Formation | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance = instance
        self.formation = formation
        if instance is not None:
            self.fields["libelle"].initial = instance.libelle
            self.fields["date_debut"].initial = instance.date_debut
            self.fields["date_fin"].initial = instance.date_fin
            self.fields["rythme_mensuel"].initial = [instance.rythme_mensuel]
        elif formation is not None:
            self.fields["rythme_mensuel"].initial = [formation.rythme_mensuel]

    def clean_rythme_mensuel(self):
        values = [v for v in self.cleaned_data.get("rythme_mensuel", []) if v]
        if not values:
            if self.instance is not None:
                return self.instance.rythme_mensuel
            if self.formation is not None:
                return self.formation.rythme_mensuel
            return Formation.RythmeMensuel.TOUT_LE_MOIS
        if len(values) > 1:
            raise forms.ValidationError("Sélectionnez une seule contrainte de rythme mensuel.")
        return values[0]

    def clean(self):
        cleaned = super().clean()
        debut = cleaned.get("date_debut")
        fin = cleaned.get("date_fin")
        if debut and fin and fin < debut:
            raise forms.ValidationError("La date de fin doit être postérieure à la date de début.")
        return cleaned


class FormationModuleForm(forms.ModelForm):
    """Formulaire d'ajout d'un module à une formation avec dates et volume horaire."""

    sites = forms.ModelMultipleChoiceField(
        queryset=Site.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple(),
        label="Sites",
    )
    batiments = forms.ModelMultipleChoiceField(
        queryset=Batiment.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple(),
        label="Bâtiments",
    )
    salles = forms.ModelMultipleChoiceField(
        queryset=Salle.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple(),
        label="Salles",
    )
    grade_cible = forms.MultipleChoiceField(
        choices=[],
        required=True,
        widget=forms.CheckboxSelectMultiple(),
        label="Grades concernés",
    )
    modules = forms.ModelMultipleChoiceField(
        queryset=Module.objects.none(),
        required=False,
        label="Modules",
    )

    def __init__(self, *args, formation=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.formation = formation
        self.fields["module"].queryset = Module.objects.filter(actif=True).order_by("titre")
        self.fields["module"].required = False
        self.fields["modules"].queryset = Module.objects.filter(actif=True).order_by("titre")
        periodes_qs = FormationPeriode.objects.none()
        if formation is not None:
            periodes_qs = FormationPeriode.objects.filter(formation_id=formation.pk).order_by("ordre", "date_debut")
        self.fields["periode"].queryset = periodes_qs
        if formation is not None and periodes_qs.exists() and not self.is_bound:
            self.fields["periode"].initial = periodes_qs.first().pk
        grades = list(Grade.objects.filter(actif=True).order_by("ordre", "libelle").values_list("libelle", flat=True))
        self.fields["grade_cible"].choices = [("__ALL__", "Tous les grades")] + [(g, g) for g in grades]

        # Sites toujours visibles.
        self.fields["sites"].queryset = Site.objects.filter(actif=True).order_by("nom")

        selected_site_ids = []
        selected_batiment_ids = []
        if self.is_bound:
            selected_site_ids = [int(v) for v in self.data.getlist("sites") if str(v).isdigit()]
            selected_batiment_ids = [int(v) for v in self.data.getlist("batiments") if str(v).isdigit()]
        else:
            selected_site_ids = [int(v) for v in (self.initial.get("sites") or []) if str(v).isdigit()]
            selected_batiment_ids = [int(v) for v in (self.initial.get("batiments") or []) if str(v).isdigit()]

        # Bâtiments visibles uniquement si site sélectionné.
        batiments_qs = Batiment.objects.filter(actif=True).order_by("nom")
        if selected_site_ids:
            batiments_qs = batiments_qs.filter(site_id__in=selected_site_ids)
        else:
            batiments_qs = Batiment.objects.none()
        self.fields["batiments"].queryset = batiments_qs

        # Salles : bâtiments cochés si présents, sinon toutes les salles des sites cochés
        # (site seul = tout le périmètre du site au planning).
        salles_qs = Salle.objects.filter(actif=True).order_by("nom")
        if selected_batiment_ids:
            salles_qs = salles_qs.filter(batiment_id__in=selected_batiment_ids)
        elif selected_site_ids:
            salles_qs = salles_qs.filter(
                batiment_id__in=Batiment.objects.filter(actif=True, site_id__in=selected_site_ids).values_list(
                    "pk", flat=True
                )
            )
        else:
            salles_qs = Salle.objects.none()
        self.fields["salles"].queryset = salles_qs

    @staticmethod
    def _selected_pk_strs(bound_field) -> frozenset[str]:
        raw = bound_field.value()
        if not raw:
            return frozenset()
        return frozenset(str(x) for x in raw)

    @property
    def selected_site_id_strs(self) -> frozenset[str]:
        return self._selected_pk_strs(self["sites"])

    @property
    def selected_batiment_id_strs(self) -> frozenset[str]:
        return self._selected_pk_strs(self["batiments"])

    @property
    def selected_salle_id_strs(self) -> frozenset[str]:
        return self._selected_pk_strs(self["salles"])

    @property
    def selected_module_id_strs(self) -> list[str]:
        if self.is_bound:
            values = [v for v in self.data.getlist("modules") if str(v).isdigit()]
        else:
            values = [str(x) for x in (self.initial.get("modules") or [])]
        return sorted(values, key=lambda v: int(v))

    def clean(self):
        cleaned_data = super().clean()
        modules = list(cleaned_data.get("modules") or [])
        module = cleaned_data.get("module")
        if not modules:
            if module:
                modules = [module]
            else:
                raise forms.ValidationError({"modules": "Sélectionnez au moins un module."})
        cleaned_data["modules"] = modules
        return cleaned_data

    def clean_grade_cible(self):
        """Valide la sélection des grades (un, plusieurs ou tous)."""
        grades = [g.strip().upper() for g in self.cleaned_data.get("grade_cible", []) if g.strip()]
        if not grades:
            raise forms.ValidationError("Sélectionnez au moins un grade ou 'Tous les grades'.")
        if "__ALL__" in grades:
            return ["__ALL__"]
        return grades

    class Meta:
        model = FormationModule
        fields = [
            "periode",
            "grade_cible",
            "module",
            "creneau_mode",
        ]
        widgets = {
            "periode": forms.Select(attrs={"class": "form-select"}),
            "module": forms.Select(attrs={"class": "form-select"}),
            "creneau_mode": forms.Select(attrs={"class": "form-select"}),
        }
        labels = {
            "periode": "Période",
            "creneau_mode": "Créneaux autorisés",
        }


class ImportFormateursForm(forms.Form):
    """Formulaire d'import du référentiel formateurs (POST fichier uniquement)."""

    fichier = forms.FileField(
        widget=forms.FileInput(attrs={"class": "form-control", "accept": ".xlsx,.xls"}),
        label="Fichier Excel (.xlsx)",
    )
