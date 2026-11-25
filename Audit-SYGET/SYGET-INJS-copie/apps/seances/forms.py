from django import forms

from apps.referentiels.models import Module

from .models import Seance


class GeneratePlanning(forms.Form):
    """Formulaire de confirmation de génération du planning."""

    confirmer = forms.BooleanField(
        required=True,
        label="Je confirme vouloir (re)générer le planning de ce groupe.",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )


class SeanceForm(forms.ModelForm):
    """Formulaire d'édition manuelle d'une séance."""

    module = forms.ModelChoiceField(
        queryset=Module.objects.none(),
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    class Meta:
        model = Seance
        fields = [
            "module",
            "date",
            "heure_debut",
            "heure_fin",
            "formateur_nom",
            "formateur_prenom",
            "formateur_numero",
            "formateur_email",
            "formateur_telephone",
            "formateur_organisation",
            "site_nom",
            "batiment_nom",
            "salle_nom",
        ]
        labels = {
            "module": "Module",
            "date": "Date",
            "heure_debut": "Heure début",
            "heure_fin": "Heure fin",
            "formateur_nom": "Nom",
            "formateur_prenom": "Prénom",
            "formateur_numero": "Numéro",
            "formateur_email": "E-mail",
            "formateur_telephone": "Téléphone",
            "formateur_organisation": "Organisation",
            "site_nom": "Site",
            "batiment_nom": "Bâtiment",
            "salle_nom": "Salle",
        }
        widgets = {
            "date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "heure_debut": forms.TimeInput(attrs={"class": "form-control", "type": "time"}),
            "heure_fin": forms.TimeInput(attrs={"class": "form-control", "type": "time"}),
            "formateur_nom": forms.TextInput(attrs={"class": "form-control"}),
            "formateur_prenom": forms.TextInput(attrs={"class": "form-control"}),
            "formateur_numero": forms.TextInput(attrs={"class": "form-control"}),
            "formateur_email": forms.EmailInput(attrs={"class": "form-control"}),
            "formateur_telephone": forms.TextInput(attrs={"class": "form-control"}),
            "formateur_organisation": forms.TextInput(attrs={"class": "form-control"}),
            "site_nom": forms.TextInput(attrs={"class": "form-control"}),
            "batiment_nom": forms.TextInput(attrs={"class": "form-control"}),
            "salle_nom": forms.TextInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, formation=None, **kwargs):
        super().__init__(*args, **kwargs)
        if formation is not None:
            module_ids = formation.modules.values_list("module_id", flat=True).distinct()
            self.fields["module"].queryset = Module.objects.filter(pk__in=module_ids).order_by("titre")
        else:
            self.fields["module"].queryset = Module.objects.filter(actif=True).order_by("titre")

    def clean(self):
        cleaned_data = super().clean()
        heure_debut = cleaned_data.get("heure_debut")
        heure_fin = cleaned_data.get("heure_fin")
        if heure_debut and heure_fin and heure_fin <= heure_debut:
            raise forms.ValidationError("L'heure de fin doit être postérieure à l'heure de début.")

        salle_nom = (cleaned_data.get("salle_nom") or "").strip()
        date = cleaned_data.get("date")
        if salle_nom and date and heure_debut and heure_fin:
            from django.db.models import Q

            from apps.seances.planning.locations import charger_localisations_salles, salle_id_pour_nom

            _, salle_ids = charger_localisations_salles()
            salle_pk = salle_id_pour_nom(salle_nom, salle_ids)
            overlap_q = Q(salle_nom__iexact=salle_nom)
            if salle_pk:
                overlap_q |= Q(salle_id=salle_pk)
            qs = Seance.objects.filter(
                overlap_q,
                date=date,
                heure_debut__lt=heure_fin,
                heure_fin__gt=heure_debut,
            )
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                autre = qs.select_related("groupe").first()
                raise forms.ValidationError(
                    "Ce créneau est déjà utilisé : la salle « %(salle)s » est occupée le %(date)s "
                    "par le groupe « %(groupe)s » (ou une autre séance). Choisissez une autre salle, "
                    "une autre date ou un autre horaire."
                    % {
                        "salle": salle_nom,
                        "date": date.strftime("%d/%m/%Y"),
                        "groupe": autre.groupe.nom if autre else "—",
                    }
                )

        formateur_nom = (cleaned_data.get("formateur_nom") or "").strip()
        cleaned_data["formateur_nom"] = formateur_nom
        cleaned_data["formateur_prenom"] = (cleaned_data.get("formateur_prenom") or "").strip()
        cleaned_data["formateur_numero"] = (cleaned_data.get("formateur_numero") or "").strip()
        cleaned_data["formateur_email"] = (cleaned_data.get("formateur_email") or "").strip()
        cleaned_data["formateur_telephone"] = (cleaned_data.get("formateur_telephone") or "").strip()
        cleaned_data["formateur_organisation"] = (cleaned_data.get("formateur_organisation") or "").strip()
        if formateur_nom and date:
            max_seances_jour = 2
            count_qs = Seance.objects.filter(
                date=date,
                formateur_nom__iexact=formateur_nom,
            )
            if self.instance.pk:
                count_qs = count_qs.exclude(pk=self.instance.pk)
            if count_qs.count() >= max_seances_jour:
                raise forms.ValidationError(
                    "Le formateur « %(formateur)s » a déjà atteint la limite de %(max)s séance(s) le %(date)s."
                    % {
                        "formateur": formateur_nom,
                        "max": max_seances_jour,
                        "date": date.strftime("%d/%m/%Y"),
                    }
                )

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        from apps.seances.planning.locations import charger_localisations_salles, salle_id_pour_nom

        _, salle_ids = charger_localisations_salles()
        instance.salle_id = salle_id_pour_nom(instance.salle_nom or "", salle_ids)

        from apps.formations.models import Formateur

        numero = (instance.formateur_numero or "").strip()
        email = (instance.formateur_email or "").strip()
        ref = None
        if numero:
            ref = Formateur.objects.filter(numero=numero).first()
        if ref is None and email:
            ref = Formateur.objects.filter(email__iexact=email).first()
        instance.formateur_referentiel = ref

        if commit:
            instance.save()
        return instance
