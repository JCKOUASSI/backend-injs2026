from django import forms

from .models import ConfigGroupe, Groupe

JOURS_CHOICES = [
    (0, "Lundi"),
    (1, "Mardi"),
    (2, "Mercredi"),
    (3, "Jeudi"),
    (4, "Vendredi"),
    (5, "Samedi"),
    (6, "Dimanche"),
]

_TIME_WIDGET = forms.TimeInput(
    format="%H:%M",
    attrs={"class": "form-control", "type": "time", "step": "60"},
)
_TIME_FIELD_NAMES = (
    "matin_heure_debut",
    "matin_heure_fin",
    "soir_heure_debut",
    "soir_heure_fin",
)


class GroupeForm(forms.ModelForm):
    """Formulaire de création d'un groupe."""

    class Meta:
        model = Groupe
        fields = ["nom", "max_auditeurs"]
        widgets = {
            "nom": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ex: A4_GROUPE1"}),
            "max_auditeurs": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
        }


class ConfigHorairesForm(forms.ModelForm):
    """Formulaire de configuration des horaires d'un groupe."""

    class Meta:
        model = ConfigGroupe
        fields = [
            "matin_actif",
            "matin_heure_debut",
            "matin_heure_fin",
            "soir_actif",
            "soir_heure_debut",
            "soir_heure_fin",
        ]
        widgets = {
            "matin_actif": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "matin_heure_debut": _TIME_WIDGET,
            "matin_heure_fin": _TIME_WIDGET,
            "soir_actif": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "soir_heure_debut": _TIME_WIDGET,
            "soir_heure_fin": _TIME_WIDGET,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in _TIME_FIELD_NAMES:
            self.fields[name].input_formats = ["%H:%M", "%H:%M:%S"]
            self.fields[name].widget.format = "%H:%M"


class JoursCoursForm(forms.Form):
    """Formulaire de sélection des jours de cours actifs."""

    jours = forms.MultipleChoiceField(
        choices=JOURS_CHOICES,
        widget=forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
        required=False,
        label="Jours de cours",
    )

    def clean_jours(self) -> list[int]:
        """Convertit les choix en liste d'entiers."""
        return [int(j) for j in self.cleaned_data.get("jours", [])]


class RythmeMensuelGroupeForm(forms.Form):
    """Formulaire pour la cadence mensuelle d'un groupe.

    Affiché en cases à cocher. Aucune case cochée ⇒ le groupe hérite de la
    cadence de la formation. Une seule case cochée ⇒ override pour ce groupe.
    """

    rythme_mensuel = forms.MultipleChoiceField(
        choices=Groupe.RythmeMensuel.choices,
        widget=forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
        required=False,
        label="Cadence du groupe (semaines par mois)",
        help_text=(
            "Aucune case cochée ⇒ le groupe hérite de la cadence de la formation. "
            "Sinon, coche une seule case pour la remplacer (override) pour ce groupe."
        ),
    )

    def clean_rythme_mensuel(self) -> str:
        values = [v for v in self.cleaned_data.get("rythme_mensuel", []) if v]
        if not values:
            return ""
        if len(values) > 1:
            raise forms.ValidationError("Sélectionnez au plus une cadence pour le groupe (ou aucune pour hériter).")
        return values[0]
