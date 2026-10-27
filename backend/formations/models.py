import uuid
from django.db import models
from django.db.models.functions import Lower
from django.conf import settings
from django.utils import timezone


class Secretariat(models.Model):
    """Secrétariat qui gère ses participants."""

    numero = models.CharField(max_length=50, unique=True, blank=True)
    nom = models.CharField(max_length=255, help_text="Nom du secrétariat")
    type = models.ForeignKey(
        'RefTypeSecretariat',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='secretariats',
        help_text="Type de secrétariat",
    )
    description = models.TextField(blank=True, default='')
    responsable = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='secretariats_resp',
        limit_choices_to={'role': 'CHEF_SECRETARIAT'},
    )
    # Modèle fonctionnel §15 : « un secrétariat est rattaché à une structure » —
    # le secrétariat devient un service de support de l'organigramme (rattachement
    # optionnel, au plus un parmi direction/département ; l'entité reste autonome
    # tant que le rattachement n'est pas posé).
    direction = models.ForeignKey(
        'administrations.Direction', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='secretariats', verbose_name='Direction de rattachement',
    )
    departement = models.ForeignKey(
        'administrations.Departement', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='secretariats', verbose_name='Département de rattachement',
    )
    adjoint = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='secretariats_adjoint', verbose_name='Adjoint(e)',
    )
    telephone = models.CharField(max_length=30, blank=True, default='', verbose_name='Téléphone')
    email = models.EmailField(blank=True, default='', verbose_name='E-mail')
    localisation = models.CharField(max_length=150, blank=True, default='',
                                    verbose_name='Localisation')
    actif = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['nom']
        verbose_name = 'Secrétariat'
        verbose_name_plural = 'Secrétariats'
        constraints = [
            models.CheckConstraint(
                check=(models.Q(direction__isnull=True) | models.Q(departement__isnull=True)),
                name='secretariat_rattache_au_plus_un',
            ),
        ]

    def save(self, *args, **kwargs):
        if not self.numero:
            from django.db import transaction
            with transaction.atomic():
                last = Secretariat.objects.select_for_update().order_by('-id').first()
                next_id = (last.id + 1) if last else 1
                self.numero = f'S{next_id:04d}'
                while Secretariat.objects.filter(numero=self.numero).exists():
                    next_id += 1
                    self.numero = f'S{next_id:04d}'
                super().save(*args, **kwargs)
        else:
            super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.nom} ({self.numero})"

    @property
    def nb_participants(self):
        return self.participants.count()

    @property
    def nb_formations(self):
        return self.modules_secretariat.values('formation_id').distinct().count()

    @property
    def nb_modules(self):
        return self.modules_secretariat.count()


class RefTypeSecretariat(models.Model):
    """Types de secrétariat (référentiel configurable)."""
    libelle = models.CharField(max_length=100, unique=True)
    actif = models.BooleanField(default=True)

    class Meta:
        ordering = ['libelle']
        verbose_name = 'Référentiel – Type de secrétariat'
        verbose_name_plural = 'Référentiel – Types de secrétariat'

    def __str__(self):
        return self.libelle


class RefCategorie(models.Model):
    """Catégories prédéfinies."""
    libelle = models.CharField(max_length=100, unique=True)
    actif = models.BooleanField(default=True)

    class Meta:
        ordering = ['libelle']
        verbose_name = 'Référentiel – Catégorie'
        verbose_name_plural = 'Référentiel – Catégories'

    def __str__(self):
        return self.libelle


class RefGrade(models.Model):
    """Grades prédéfinis, liés à une catégorie."""
    categorie = models.ForeignKey(
        RefCategorie, on_delete=models.CASCADE, related_name='grades',
        null=True, blank=True,
    )
    libelle = models.CharField(max_length=100)
    actif = models.BooleanField(default=True)

    class Meta:
        ordering = ['libelle']
        unique_together = ('categorie', 'libelle')
        verbose_name = 'Référentiel – Grade'
        verbose_name_plural = 'Référentiel – Grades'

    def __str__(self):
        return self.libelle


class RefVague(models.Model):
    """Vagues prédéfinies (ex: PREMIERE VAGUE, DEUXIEME VAGUE…)."""
    libelle = models.CharField(max_length=100, unique=True)
    ordre = models.PositiveSmallIntegerField(default=1, help_text="Ordre d'affichage")
    actif = models.BooleanField(default=True)

    class Meta:
        ordering = ['ordre', 'libelle']
        verbose_name = 'Référentiel – Vague'
        verbose_name_plural = 'Référentiel – Vagues'

    def __str__(self):
        return self.libelle


class RefFormation(models.Model):
    """Cycle de formation du référentiel (modèle fonctionnel 04.4) : le descripteur
    administratif et pédagogique d'un cursus — la *formation opérationnelle*
    (``Formation``, session ouverte) s'y adosse par ``ref_formation`` (lien D3)."""

    class TypeDiplome(models.TextChoices):
        LICENCE = 'LICENCE', 'Licence'
        MASTER = 'MASTER', 'Master'
        DOCTORAT = 'DOCTORAT', 'Doctorat'
        DUT = 'DUT', 'DUT / BTS'
        PROFESSIONNALISANT = 'PROFESSIONNALISANT', 'Cycle professionnalisant'
        AUTRE = 'AUTRE', 'Autre'

    class Perimetre(models.TextChoices):
        """L6 — qualification de la ligne au regard du référentiel métier INJS.

        Une ligne ``INJS`` est une formation validée par la source métier
        (docs/audits/A-4.5 §2, nomenclature des 8 filières). Une ligne
        ``LEGACY`` provient d'un autre corpus 
        professorat) et n'appartient pas au référentiel INJS. ``NON_DETERMINE``
        est l'état par défaut : aucune valeur n'est inventée.
        """

        INJS = 'INJS', 'INJS validé'
        LEGACY = 'LEGACY', 'Legacy / autre source'
        NON_DETERMINE = 'NON_DETERMINE', 'Non déterminé'

    intitule = models.CharField(max_length=255, unique=True)
    actif = models.BooleanField(default=True)
    # --- Lot L6 (référentiel officiel INJS) : qualification + traçabilité ---
    perimetre = models.CharField(
        max_length=20, choices=Perimetre.choices, default=Perimetre.NON_DETERMINE,
        db_index=True,
        help_text='L6 : INJS = filière validée par la source métier ; LEGACY = corpus '
                  'étranger exclu du référentiel INJS.',
    )
    filiere_code = models.CharField(
        max_length=10, blank=True, default='', db_index=True,
        help_text='L6 : code stable de la filière métier (F01…F08) — voir docs/audits/'
                  'A-4.5 §2. Vide si la ligne n\'est rattachée à aucune filière validée.',
    )
    source = models.CharField(
        max_length=100, blank=True, default='',
        help_text='L6 : référence de la source métier ayant attesté la ligne.',
    )
    # --- Lot B refonte (modèle 04.4) : descripteur de cycle ---
    code = models.CharField(max_length=30, blank=True, default='', db_index=True,
                            help_text='Code court du cycle (ex. LIC-ADMIN).')
    type_diplome = models.CharField(max_length=20, blank=True, default='',
                                    choices=TypeDiplome.choices, verbose_name='Type de diplôme')
    domaine = models.CharField(max_length=100, blank=True, default='')
    mention = models.CharField(max_length=100, blank=True, default='')
    duree_annees = models.PositiveSmallIntegerField(null=True, blank=True,
                                                     verbose_name='Durée (années)')
    nb_semestres = models.PositiveSmallIntegerField(null=True, blank=True,
                                                     verbose_name='Nombre de semestres')
    nb_credites = models.PositiveSmallIntegerField(null=True, blank=True,
                                                   verbose_name='Crédits ECTS visés')
    description = models.TextField(blank=True, default='')
    prix_heure_realisee = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Prix pour 1 heure réalisée',
        help_text='Tarif horaire spécifique. Si non renseigné, le tarif par défaut des paramètres finance s\'applique.',
    )

    class Meta:
        ordering = ['intitule']
        verbose_name = 'Référentiel – Formation (cycle)'
        verbose_name_plural = 'Référentiel – Formations (cycles)'

    def __str__(self):
        return self.intitule


class RefModule(models.Model):
    """Modules/cours prédéfinis (ex: Déontologie de la Fonction Publique)."""
    formations = models.ManyToManyField(
        RefFormation,
        related_name='modules',
        help_text="Formation(s) (cycle) auxquelles appartient ce module",
    )
    intitule = models.CharField(max_length=255)
    volume_horaire = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    actif = models.BooleanField(default=True)

    class Meta:
        ordering = ['intitule']
        verbose_name = 'Référentiel – Module'
        verbose_name_plural = 'Référentiel – Modules'
        constraints = [
            models.UniqueConstraint(Lower('intitule'), name='uniq_refmodule_intitule_ci'),
        ]

    @staticmethod
    def normalize_intitule(value):
        """Normalise un intitulé : trim, espaces multiples → un seul, majuscules."""
        if value is None:
            return ''
        return ' '.join(str(value).split()).upper()

    @classmethod
    def resolve_for_intitule(cls, intitule):
        """Retrouve le RefModule dont l'intitulé correspond exactement (après normalisation)."""
        norm = cls.normalize_intitule(intitule)
        if not norm:
            return None
        return cls.objects.filter(intitule__iexact=norm).first()

    @classmethod
    def resolve_for_module(cls, module):
        """Retrouve le RefModule lié à un module opérationnel (FK ou intitulé exact)."""
        if module is None:
            return None
        if getattr(module, 'ref_module_id', None) and getattr(module, 'ref_module', None):
            return module.ref_module
        return cls.resolve_for_intitule(getattr(module, 'intitule', None))

    def save(self, *args, **kwargs):
        self.intitule = RefModule.normalize_intitule(self.intitule)
        super().save(*args, **kwargs)

    def __str__(self):
        # Parcourt all() pour réutiliser un prefetch_related éventuel de l'appelant.
        labels = sorted(formation.intitule for formation in self.formations.all())
        if labels:
            return f"{self.intitule} ({', '.join(labels)})"
        return self.intitule

    def get_volume_horaire_for_formation_categorie(self, formation_id=None, formation_intitule=None, categorie_code=None):
        """Volume horaire pour une formation (cycle) et une catégorie données."""
        qs = self.volumes_horaires.select_related('formation', 'categorie')
        if formation_id:
            qs = qs.filter(formation_id=formation_id)
        elif formation_intitule:
            qs = qs.filter(formation__intitule__iexact=str(formation_intitule).strip())
        if categorie_code:
            code = str(categorie_code).strip()
            entry = qs.filter(categorie__libelle__iexact=code).first()
            if not entry and len(code) == 1:
                entry = qs.filter(categorie__libelle__iexact=code).first() or qs.filter(
                    categorie__libelle__istartswith=code,
                ).first()
            if entry and entry.volume_horaire is not None:
                return entry.volume_horaire
        if formation_id or formation_intitule:
            return None
        return self.volume_horaire

    def get_volume_horaire_for_categorie(self, categorie_code):
        """Compatibilité : volume pour une catégorie (sans formation précise)."""
        if not categorie_code:
            return self.volume_horaire
        try:
            volume_par_cat = self.volumes_horaires.filter(
                categorie__libelle__iexact=categorie_code,
            ).first()
            if not volume_par_cat:
                code = str(categorie_code).strip()
                if len(code) == 1:
                    volume_par_cat = self.volumes_horaires.filter(
                        categorie__libelle__istartswith=code,
                    ).first()
            if volume_par_cat and volume_par_cat.volume_horaire is not None:
                return volume_par_cat.volume_horaire
        except Exception:
            pass
        return self.volume_horaire


class RefModuleVolumeHoraire(models.Model):
    """Volume horaire d'un module pour une formation (cycle) et une catégorie."""

    module = models.ForeignKey(
        RefModule,
        on_delete=models.CASCADE,
        related_name='volumes_horaires',
        help_text="Module du référentiel",
    )
    formation = models.ForeignKey(
        RefFormation,
        on_delete=models.CASCADE,
        related_name='volumes_horaires_modules',
        help_text="Formation (cycle) concernée",
    )
    categorie = models.ForeignKey(
        RefCategorie,
        on_delete=models.CASCADE,
        related_name='volumes_horaires_modules',
        help_text="Catégorie concernée (A, B, C, D...)",
    )
    volume_horaire = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Volume horaire pour cette catégorie (en heures)",
    )

    class Meta:
        ordering = ['module', 'formation__intitule', 'categorie__libelle']
        verbose_name = 'Référentiel – Volume horaire (formation × catégorie)'
        verbose_name_plural = 'Référentiel – Volumes horaires (formation × catégorie)'
        unique_together = ('module', 'formation', 'categorie')

    def __str__(self):
        return (
            f"{self.module.intitule} – {self.formation.intitule} – "
            f"{self.categorie.libelle} : {self.volume_horaire}h"
        )


class RefSite(models.Model):
    """Sites/centres de formation prédéfinis."""
    nom = models.CharField(max_length=255, unique=True)
    actif = models.BooleanField(default=True)
    geofence_latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Latitude du centre de formation (contrôle de présence mobile)",
    )
    geofence_longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Longitude du centre de formation",
    )
    geofence_rayon_m = models.PositiveIntegerField(
        default=200,
        help_text="Rayon autorisé en mètres pour le badgeage mobile",
    )

    class Meta:
        ordering = ['nom']
        verbose_name = 'Référentiel – Site'
        verbose_name_plural = 'Référentiel – Sites'

    def __str__(self):
        return self.nom


class RefBatiment(models.Model):
    """Bâtiments rattachés à un site."""
    site = models.ForeignKey(RefSite, on_delete=models.CASCADE, related_name='batiments')
    nom = models.CharField(max_length=255)
    actif = models.BooleanField(default=True)

    class Meta:
        ordering = ['nom']
        unique_together = ('site', 'nom')
        verbose_name = 'Référentiel – Bâtiment'
        verbose_name_plural = 'Référentiel – Bâtiments'

    def __str__(self):
        return f"{self.nom} ({self.site.nom})"


class RefSalle(models.Model):
    """Salles rattachées à un bâtiment (ou directement à un site)."""

    class TypeLieu(models.TextChoices):
        SALLE = 'SALLE', 'Salle'
        AMPHI = 'AMPHI', 'Amphithéâtre'
        GYMNASE = 'GYMNASE', 'Gymnase'
        REUNION = 'REUNION', 'Salle de réunion'
        CONFERENCE = 'CONFERENCE', 'Salle de conférence'
        # Lot L8 (étape H) — types ajoutés pour rendre la contrainte forte C7
        # (compatibilité salle / type d'enseignement CM·TD·TP) évaluable par le
        # moteur. Aucun reclassement automatique : les 58 salles restent SALLE
        # tant que l'INJS ne les requalifie pas.
        COURS = 'COURS', 'Salle de cours'
        TD = 'TD', 'Salle de TD'
        TP = 'TP', 'Salle de travaux pratiques'
        INFORMATIQUE = 'INFORMATIQUE', 'Salle informatique'
        LABORATOIRE = 'LABORATOIRE', 'Laboratoire'
        SPORT = 'SPORT', 'Espace sportif couvert'

    site = models.ForeignKey(RefSite, on_delete=models.CASCADE, related_name='salles')
    batiment = models.ForeignKey(RefBatiment, on_delete=models.SET_NULL, null=True, blank=True, related_name='salles')
    nom = models.CharField(max_length=100)
    type_lieu = models.CharField(max_length=20, choices=TypeLieu.choices, default=TypeLieu.SALLE)
    capacite = models.PositiveIntegerField(null=True, blank=True)
    equipements = models.CharField(max_length=255, blank=True, default='')
    # Lot L10 — types d'espaces sportifs (référentiel du lot L5)
    type_espace = models.ForeignKey(
        'referentiels.RefTypeEspaceSportif', on_delete=models.SET_NULL,
        related_name='salles', null=True, blank=True,
        help_text="Type d'espace sportif (gymnase, piscine, terrain…).",
    )
    indisponible_du = models.DateField(null=True, blank=True)
    indisponible_au = models.DateField(null=True, blank=True)
    actif = models.BooleanField(default=True)

    class Meta:
        ordering = ['nom']
        unique_together = ('site', 'batiment', 'nom')
        verbose_name = 'Référentiel – Salle'
        verbose_name_plural = 'Référentiel – Salles'

    def __str__(self):
        return f"{self.nom} – {self.site.nom}"


class Formation(models.Model):

    numero_formation = models.PositiveSmallIntegerField(null=True, blank=True, help_text="N° de la formation dans le cycle")
    formation = models.CharField(max_length=255)
    # Lien D3 résolu (lot B refonte) : la session ouverte s'adosse au cycle du
    # référentiel. Nullable + SET_NULL : aucune formation existante n'est
    # contrainte, la chaîne LMD (parcours/maquettes/EDT) peut la remonter.
    ref_formation = models.ForeignKey(
        RefFormation, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='formations', verbose_name='Cycle de référence',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['formation']
        verbose_name = 'Formation'
        verbose_name_plural = 'Formations'

    def __str__(self):
        return f"{self.formation}"


class Participant(models.Model):
    class Sexe(models.TextChoices):
        MASCULIN = 'MASCULIN', 'Masculin'
        FEMININ = 'FEMININ', 'Féminin'

    matricule = models.CharField(max_length=50, unique=True)
    nom = models.CharField(max_length=100)
    prenom = models.CharField(max_length=100)
    sexe = models.CharField(max_length=10, choices=Sexe.choices, blank=True, default='')
    date_naissance = models.DateField(null=True, blank=True)
    lieu_naissance = models.CharField(max_length=255, blank=True, default='')
    email = models.EmailField(blank=True, default='')
    telephone = models.CharField(max_length=20, blank=True, default='')
    telephone2 = models.CharField(max_length=20, blank=True, default='')
    type_concours = models.CharField(max_length=100, blank=True, default='')
    libelle_concours = models.CharField(max_length=255, blank=True, default='')
    categorie = models.CharField(max_length=100, blank=True, default='')
    grade = models.CharField(max_length=100, blank=True, default='')
    groupe = models.CharField(max_length=50, blank=True, default='')
    grade_groupe = models.CharField(max_length=150, blank=True, default='')
    vague = models.CharField(max_length=50, blank=True, default='', help_text="Vague (PREMIERE VAGUE, DEUXIEME VAGUE…)")
    site = models.CharField(max_length=255, blank=True, default='')
    salle = models.CharField(max_length=100, blank=True, default='')
    secretariat = models.ForeignKey(
        Secretariat,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='participants',
        help_text="Secrétariat responsable de ce participant",
    )
    motif_notoire = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text='Motif de notoriété du participant',
    )
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='participant_profile',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['nom', 'prenom']
        verbose_name = 'Étudiant'
        verbose_name_plural = 'Étudiants'

    def save(self, *args, **kwargs):
        from django.core.exceptions import ValidationError

        self.matricule = (self.matricule or '').strip()
        if not self.matricule:
            raise ValidationError('Le matricule est obligatoire pour un participant.')
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.nom} {self.prenom} ({self.matricule})"


class ModuleParticipant(models.Model):
    """Liste des participants ATTENDUS pour un module."""
    module = models.ForeignKey(
        'Module',
        on_delete=models.CASCADE,
        related_name='module_participants',
    )
    participant = models.ForeignKey(
        Participant,
        on_delete=models.CASCADE,
        related_name='modules_inscrits',
    )
    inscrit_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('module', 'participant')
        verbose_name = 'Inscription module'
        verbose_name_plural = 'Inscriptions modules'

    def __str__(self):
        return f"{self.participant} → {self.module.intitule}"

    @property
    def formation(self):
        """Accès rapide à la formation via le module."""
        return self.module.formation


FormationParticipant = ModuleParticipant


class Formateur(models.Model):
    numerobadge = models.CharField(max_length=50, unique=True)
    nom = models.CharField(max_length=100)
    prenom = models.CharField(max_length=100)
    email = models.EmailField(blank=True, default='')
    telephone = models.CharField(max_length=20, blank=True, default='')
    specialite = models.CharField(max_length=255, blank=True, default='')
    organisation = models.CharField(max_length=255, blank=True, default='')
    # Lot L3/L7 — distinction explicite grade / fonction / statut enseignant
    grade_ref = models.ForeignKey(
        'RefGrade', on_delete=models.SET_NULL,
        related_name='formateurs_lmd', null=True, blank=True,
        verbose_name='Grade (référentiel)',
    )
    fonction = models.CharField(
        max_length=100, blank=True, default='',
        help_text="Fonction administrative (ex : Chef de département).",
    )
    statut_enseignant = models.CharField(
        max_length=100, blank=True, default='',
        help_text="Statut de l'enseignant (ex : Titulaire, Vacataire, Contractuel).",
    )
    numero_piece_identite = models.CharField(
        max_length=100,
        blank=True,
        default='',
        verbose_name="N° pièce d'identité",
    )
    numero_compte_bancaire = models.CharField(
        max_length=100,
        blank=True,
        default='',
        verbose_name='N° de compte bancaire',
    )
    observations = models.TextField(
        blank=True,
        default='',
        verbose_name='Observations',
        help_text="Notes / observations libres sur le formateur (consultables par les archives).",
    )
    secretariats = models.ManyToManyField(
        Secretariat,
        blank=True,
        related_name='formateurs',
        help_text="Secrétariats auxquels appartient ce formateur",
    )
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='formateur_profile',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['nom', 'prenom']
        verbose_name = 'Formateur'
        verbose_name_plural = 'Formateurs'

    def save(self, *args, **kwargs):
        if not self.numerobadge:
            from django.db import transaction
            with transaction.atomic():
                last = Formateur.objects.select_for_update().order_by('-id').first()
                next_id = (last.id + 1) if last else 1
                candidate = f'F{next_id:04d}'
                while Formateur.objects.filter(numerobadge=candidate).exists():
                    next_id += 1
                    candidate = f'F{next_id:04d}'
                self.numerobadge = candidate
                super().save(*args, **kwargs)
        else:
            super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.nom} {self.prenom} ({self.numerobadge})"


class ModuleFormateur(models.Model):
    """Liste des formateurs assignés à un module."""
    module = models.ForeignKey(
        'Module',
        on_delete=models.CASCADE,
        related_name='module_formateurs',
    )
    formateur = models.ForeignKey(
        Formateur,
        on_delete=models.CASCADE,
        related_name='modules_assignes',
    )
    inscrit_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('module', 'formateur')
        verbose_name = 'Formateur assigné'
        verbose_name_plural = 'Formateurs assignés'

    @property
    def formation(self):
        return self.module.formation

    def __str__(self):
        return f"{self.formateur} → {self.module.intitule}"


FormationFormateur = ModuleFormateur


class Module(models.Model):
    """Module d'une formation (un cours). Une formation peut avoir plusieurs modules."""

    class Statut(models.TextChoices):
        PLANIFIEE  = 'PLANIFIEE',  'Planifiée'
        EN_COURS   = 'EN_COURS',   'En cours'
        SUSPENDUE  = 'SUSPENDUE',  'Suspendue'
        TERMINEE   = 'TERMINEE',   'Terminée'

    formation = models.ForeignKey(
        Formation,
        on_delete=models.CASCADE,
        related_name='modules',
    )
    intitule = models.CharField(max_length=255, help_text="Intitulé du module/cours")
    ref_module = models.ForeignKey(
        RefModule,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='modules_instances',
        help_text='Référentiel canonique du module (nomenclature unifiée)',
    )
    # Colonne historique / contrainte SQL (NOT NULL) — alignée sur le titre de formation (cycle).
    cycle = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text="Libellé du cycle de formation (ex. même valeur que Formation.formation)",
    )
    duree_prevue_heures = models.DecimalField(
        max_digits=6, decimal_places=2, default=0,
        null=True, blank=True,
        help_text="Volume horaire prévu pour ce module",
    )
    ordre = models.PositiveSmallIntegerField(default=1, help_text="Ordre d'affichage")

    grade    = models.CharField(max_length=100, blank=True, default='', help_text="Grade (profil INJS ou A4, A3…)")
    groupe   = models.CharField(max_length=50, blank=True, default='', help_text="Groupe (GROUPE 1, GROUPE 2…)")
    vague    = models.CharField(max_length=50, blank=True, default='', help_text="Vague (PREMIERE VAGUE, DEUXIEME VAGUE…)")
    secretariat = models.ForeignKey(
        Secretariat,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='modules_secretariat',
        help_text="Secrétariat responsable de ce module",
    )
    # NOTE: historiquement un champ texte. On le garde temporairement pour compat/migration.
    site_legacy = models.CharField(
        max_length=255,
        blank=True,
        default='',
        verbose_name='Site (legacy)',
        help_text="Ancien champ texte. Utiliser le champ FK « site » (RefSite) à la place.",
    )
    site = models.ForeignKey(
        RefSite,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='modules',
        verbose_name='Site',
        help_text="Centre de formation (référentiel). Sert à la géolocalisation mobile.",
    )
    batiment = models.CharField(
        max_length=255,
        blank=True,
        default='',
        verbose_name='Bâtiment',
        help_text="Bâtiment ou zone (import Excel : colonne « Bâtiment »).",
    )
    salle = models.CharField(
        max_length=100,
        blank=True,
        default='',
        verbose_name='Salle',
        help_text="Salle ou lieu précis (import Excel : colonne « Salle »).",
    )
    date_debut = models.DateField(null=True, blank=True, help_text="Date de début du module")
    date_fin   = models.DateField(null=True, blank=True, help_text="Date de fin du module")
    statut = models.CharField(
        max_length=20,
        choices=Statut.choices,
        default=Statut.PLANIFIEE,
    )
    formateur = models.ForeignKey(
        'Formateur',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='modules',
        help_text="Formateur principal du module",
    )
    superviseur = models.ForeignKey(
        'authentication.User',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='modules_supervises',
        help_text="Encadrant responsable du module",
    )
    creee_par = models.ForeignKey(
        'authentication.User',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='modules_crees',
        help_text="Utilisateur ayant créé le module",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    archived = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Module archivé : visible uniquement dans l'espace Archives.",
    )
    archived_at = models.DateTimeField(null=True, blank=True)
    archived_by = models.ForeignKey(
        'authentication.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='modules_archives',
        help_text="Utilisateur ayant archivé le module",
    )

    class Meta:
        ordering = ['ordre', 'intitule']
        verbose_name = 'Module'
        verbose_name_plural = 'Modules'
        unique_together = [('formation', 'intitule', 'grade', 'groupe', 'vague')]

    def __str__(self):
        return f"{self.intitule} ({self.formation.formation})"

    def canonical_intitule(self):
        """Libellé canonique (référentiel matière si renseigné, sinon intitulé module)."""
        if self.ref_module_id and self.ref_module:
            ref_label = (self.ref_module.intitule or '').strip()
            if ref_label:
                return ref_label
        return (self.intitule or '').strip()


class SessionModule(models.Model):
    """Une session (matin, après-midi…) d'un module pour une journée donnée."""
    module = models.ForeignKey(
        Module,
        on_delete=models.CASCADE,
        related_name='sessions',
        help_text="Module auquel appartient cette séance",
    )
    date_journee = models.DateField(default=timezone.localdate)
    numero = models.PositiveSmallIntegerField(
        help_text="Numéro de session dans la journée (1, 2, 3…)",
    )
    intitule = models.CharField(
        max_length=100, blank=True, default='',
        help_text="Intitulé libre (ex: Matin, Après-midi, Module 3…)",
    )
    heure_debut_prevue = models.TimeField(
        null=True, blank=True,
        help_text="Heure de début prévue",
    )
    heure_fin_prevue = models.TimeField(
        null=True, blank=True,
        help_text="Heure de fin prévue",
    )
    auto_demarrage = models.BooleanField(
        default=True,
        help_text="Démarrer automatiquement à l'heure prévue",
    )
    demarree_le = models.DateTimeField(null=True, blank=True)
    terminee_le = models.DateTimeField(null=True, blank=True)
    demarree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sessions_demarrees',
    )

    class Meta:
        ordering = ['date_journee', 'heure_debut_prevue', 'numero']
        unique_together = ('module', 'date_journee', 'numero')
        verbose_name = 'Séance'
        verbose_name_plural = 'Séances'

    def __str__(self):
        label = self.intitule or f"Session {self.numero}"
        module = self.module
        formation_label = module.formation.formation if module and module.formation_id else ''
        contexte_parts = [p for p in (module.grade, module.groupe, module.vague) if p]
        contexte = " / ".join(contexte_parts)
        prefixe_parts = [p for p in (formation_label, contexte) if p]
        prefixe = " | ".join(prefixe_parts)
        module_label = module.intitule if module else ''
        if self.demarree_le and not self.terminee_le:
            etat = "en cours"
        elif self.terminee_le:
            etat = "terminée"
        else:
            etat = "planifiée"
        core = f"{module_label} — {self.date_journee} {label} ({etat})"
        return f"{prefixe} • {core}" if prefixe else core

    @property
    def formation(self):
        return self.module.formation

    @property
    def est_planifiee(self):
        return self.demarree_le is None

    @property
    def est_en_cours(self):
        return self.demarree_le is not None and self.terminee_le is None

    @property
    def est_terminee(self):
        return self.terminee_le is not None

    @property
    def duree_minutes(self):
        if self.demarree_le and self.terminee_le:
            return round((self.terminee_le - self.demarree_le).total_seconds() / 60, 1)
        return None


class QRToken(models.Model):
    session = models.ForeignKey(
        SessionModule,
        on_delete=models.CASCADE,
        related_name='qr_tokens',
        null=True,
        blank=True,
        help_text="Séance liée à ce QR code",
    )
    # Lot C refonte — présence par QR sur les séances LMD de l'EDT : le même
    # jeton vit désormais pour une affectation de créneau (empilement, pas de
    # remplacement : les tokens legacy gardent leur séance).
    seance_edt = models.ForeignKey(
        'edts.AffectationCreneau',
        on_delete=models.CASCADE,
        related_name='qr_tokens',
        null=True,
        blank=True,
        help_text="Séance LMD (créneau d'emploi du temps) liée à ce QR code",
    )
    token = models.UUIDField(default=uuid.uuid4, unique=True)
    genere_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='qr_tokens_generes',
    )
    actif = models.BooleanField(default=True)
    expire_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Code QR'
        verbose_name_plural = 'Codes QR'

    @property
    def formation(self):
        return self.session.module.formation if self.session_id else None

    def __str__(self):
        if self.session_id:
            session_label = self.session.intitule or f"Session {self.session.numero}"
            label = self.session.module.intitule or self.session.module.formation.formation
            etat = 'actif' if self.actif else 'inactif'
            return f"QR {label} — {session_label} ({etat})"
        if self.seance_edt_id:
            libelle = (self.seance_edt.intitule
                       or str(self.seance_edt.creneau_template))
            etat = 'actif' if self.actif else 'inactif'
            return f"QR séance LMD — {libelle} ({etat})"
        return f"QR orphelin ({'actif' if self.actif else 'inactif'})"

    @property
    def is_expired(self):
        return timezone.now() > self.expire_at

    @property
    def is_valid(self):
        if not self.actif or self.is_expired:
            return False
        if self.session_id and self.session.est_terminee:
            return False
        if self.seance_edt_id and not self.seance_edt.actif:
            return False
        return True


class FinanceSettings(models.Model):
    """Paramètres globaux du module finance (singleton pk=1)."""
    prix_heure_realisee = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name='Prix pour 1 heure réalisée',
        help_text='Montant versé par heure de cours effectivement réalisée (badgeage).',
    )
    afficher_montants_exports = models.BooleanField(
        default=True,
        verbose_name='Afficher les montants sur les états financiers',
        help_text='Valeur par défaut lors de l\'export PDF/Excel (modifiable à chaque export).',
    )
    export_titre_document = models.CharField(
        max_length=255,
        blank=True,
        default='ÉTAT FINANCIER FORMATEUR',
        verbose_name='Titre des états financiers',
    )
    export_entete_ligne1 = models.CharField(
        max_length=255,
        blank=True,
        default='',
        verbose_name='En-tête ligne 1',
        help_text='Ex. République de Côte d\'Ivoire',
    )
    export_entete_ligne2 = models.CharField(
        max_length=255,
        blank=True,
        default='',
        verbose_name='En-tête ligne 2',
        help_text='Ex. Ministère / Direction',
    )
    export_organisme = models.CharField(
        max_length=255,
        blank=True,
        default='',
        verbose_name='Organisme',
        help_text='Nom affiché sur les états financiers.',
    )
    export_adresse = models.TextField(
        blank=True,
        default='',
        verbose_name='Adresse / coordonnées',
    )
    export_reference_prefix = models.CharField(
        max_length=30,
        blank=True,
        default='EFI',
        verbose_name='Préfixe de référence document',
    )
    export_mention_legale = models.TextField(
        blank=True,
        default='',
        verbose_name='Mention légale / pied de page',
    )
    export_signataire_nom = models.CharField(
        max_length=255,
        blank=True,
        default='',
        verbose_name='Nom du signataire',
    )
    export_signataire_fonction = models.CharField(
        max_length=255,
        blank=True,
        default='',
        verbose_name='Fonction du signataire',
    )
    export_contacts = models.TextField(
        blank=True,
        default='',
        verbose_name='Contacts (fiche récap formateur)',
        help_text='Une ligne par contact ou phrase affichée sous la note NB des exports fiche formateur.',
    )
    export_pied_page_titre = models.CharField(
        max_length=255,
        blank=True,
        default='',
        verbose_name='Titre pied de page (fiche récap)',
        help_text='Ex. DOCUMENT CONFIDENTIEL — affiché en gras en bas de la fiche formateur.',
    )
    export_pied_page_texte = models.TextField(
        blank=True,
        default='',
        verbose_name='Texte pied de page (fiche récap)',
        help_text='Coordonnées institutionnelles affichées sous le titre en bas de la fiche formateur.',
    )
    tolerance_active = models.BooleanField(
        default=False,
        verbose_name='Activer la tolérance horaire',
        help_text='Active la marge de tolérance sur les volumes réalisés inférieurs au planifié.',
    )
    tolerance_minutes = models.PositiveIntegerField(
        default=30,
        verbose_name='Tolérance (minutes)',
        help_text='Marge absolue acceptée (minutes) entre planifié et réalisé.',
    )
    tolerance_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=5,
        verbose_name='Tolérance (%)',
        help_text='Marge relative (% du volume planifié). Le seuil retenu est le plus favorable des deux.',
    )
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='finance_settings_updates',
    )

    class Meta:
        verbose_name = 'Paramètres finance'
        verbose_name_plural = 'Paramètres finance'

    def __str__(self):
        return f'Paramètres finance (1 h réalisée = {self.prix_heure_realisee})'

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(
            pk=1,
            defaults={
                'tolerance_active': False,
                'tolerance_minutes': 30,
                'tolerance_pct': 5,
            },
        )
        return obj


class FinanceAjustement(models.Model):
    """Proposition d'ajustement horaire sur une séance terminée (workflow Finance / Direction)."""

    class Statut(models.TextChoices):
        EN_ATTENTE = 'EN_ATTENTE', 'En attente'
        VALIDE = 'VALIDE', 'Validé'
        REJETE = 'REJETE', 'Rejeté'

    session = models.ForeignKey(
        SessionModule,
        on_delete=models.CASCADE,
        related_name='finance_ajustements',
    )
    formateur = models.ForeignKey(
        'Formateur',
        on_delete=models.CASCADE,
        related_name='finance_ajustements',
    )
    minutes_delta = models.IntegerField(
        help_text='Minutes à ajouter (positif) ou retirer (négatif) du volume réalisé.',
    )
    motif = models.TextField()
    statut = models.CharField(
        max_length=20,
        choices=Statut.choices,
        default=Statut.EN_ATTENTE,
        db_index=True,
    )
    realise_avant_minutes = models.FloatField(
        null=True,
        blank=True,
        help_text='Volume réalisé de la séance avant ajustement (snapshot).',
    )
    realise_apres_minutes = models.FloatField(
        null=True,
        blank=True,
        help_text='Volume réalisé attendu après validation.',
    )
    proposed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='finance_ajustements_proposes',
    )
    proposed_at = models.DateTimeField(auto_now_add=True)
    validated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='finance_ajustements_valides',
    )
    validated_at = models.DateTimeField(null=True, blank=True)
    rejected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='finance_ajustements_rejetes',
    )
    rejected_at = models.DateTimeField(null=True, blank=True)
    rejection_motif = models.TextField(blank=True, default='')

    class Meta:
        verbose_name = 'Ajustement horaire finance'
        verbose_name_plural = 'Ajustements horaires finance'
        ordering = ['-proposed_at']
        indexes = [
            models.Index(fields=['statut', 'proposed_at'], name='formations__statut_8e2f0a_idx'),
            models.Index(fields=['session', 'statut'], name='formations__session_4c1b2d_idx'),
        ]

    def __str__(self):
        return f'Ajustement {self.statut} — séance {self.session_id} ({self.minutes_delta} min)'


class NoteModuleColonne(models.Model):
    """Colonne de saisie de notes /20 (ou autre barème) pour un module."""

    module = models.ForeignKey(
        Module,
        on_delete=models.CASCADE,
        related_name='colonnes_notes',
    )
    libelle = models.CharField(max_length=120, help_text='Intitulé affiché en en-tête de colonne')
    ordre = models.PositiveSmallIntegerField(default=0)
    note_max = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=20,
        help_text='Note maximale (ex : 20)',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Colonne de note module'
        verbose_name_plural = 'Colonnes de notes module'
        ordering = ['module', 'ordre', 'id']

    def __str__(self):
        return f'{self.libelle} — {self.module}'


class NoteModule(models.Model):
    """Valeur de note d'un auditeur pour une colonne donnée."""

    colonne = models.ForeignKey(
        NoteModuleColonne,
        on_delete=models.CASCADE,
        related_name='valeurs',
    )
    participant = models.ForeignKey(
        Participant,
        on_delete=models.CASCADE,
        related_name='notes_modules',
    )
    note = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Note numérique (ex : 14.50)',
    )
    saisie_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notes_saisies',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # ── Lot L1 — Workflow de validation des notes ─────────────────────────
    class StatutValidation(models.TextChoices):
        BROUILLON = 'BROUILLON', 'Brouillon'
        SOUMISE = 'SOUMISE', 'Soumise'
        VALIDEE = 'VALIDEE', 'Validée'

    statut_validation = models.CharField(
        max_length=12,
        choices=StatutValidation.choices,
        default=StatutValidation.BROUILLON,
        help_text=(
            'Statut du workflow de validation : BROUILLON → SOUMISE → VALIDEE. '
            'Une note VALIDEE est verrouillée et ne peut plus être modifiée '
            'directement : seule une correction auditée (avec motif) est possible.'
        ),
    )
    verrouillee = models.BooleanField(
        default=False,
        help_text='True dès que la note est VALIDEE (verrouillée). '
                  'Une note verrouillée n\'est plus modifiable directement.',
    )
    validation_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notes_modules_validees',
        help_text='Utilisateur ayant validé (verrouillé) la note.',
    )
    validation_le = models.DateTimeField(
        null=True, blank=True,
        help_text='Horodatage de la validation/verrouillage.',
    )

    class Meta:
        verbose_name = 'Note module'
        verbose_name_plural = 'Notes modules'
        ordering = ['colonne', 'participant__nom', 'participant__prenom']
        unique_together = [('colonne', 'participant')]

    def __str__(self):
        return f'{self.participant} — {self.colonne}: {self.note}'


class NoteModuleSynthese(models.Model):
    """Mention et observations globales par auditeur et module."""

    class Mention(models.TextChoices):
        TRES_BIEN = 'TRES_BIEN', 'Très bien'
        BIEN = 'BIEN', 'Bien'
        ASSEZ_BIEN = 'ASSEZ_BIEN', 'Assez bien'
        PASSABLE = 'PASSABLE', 'Passable'
        INSUFFISANT = 'INSUFFISANT', 'Insuffisant'

    module = models.ForeignKey(
        Module,
        on_delete=models.CASCADE,
        related_name='syntheses_notes',
    )
    participant = models.ForeignKey(
        Participant,
        on_delete=models.CASCADE,
        related_name='syntheses_notes_modules',
    )
    mention = models.CharField(
        max_length=20,
        choices=Mention.choices,
        blank=True,
        default='',
        help_text='Mention calculée ou saisie manuellement',
    )
    observations = models.TextField(
        blank=True,
        default='',
        help_text='Observations éventuelles du secrétariat',
    )
    saisie_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='syntheses_notes_saisies',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Synthèse notes module'
        verbose_name_plural = 'Synthèses notes module'
        ordering = ['module', 'participant__nom', 'participant__prenom']
        unique_together = [('module', 'participant')]

    def __str__(self):
        return f'{self.participant} — {self.module}'


class CorrectionNoteModule(models.Model):
    """Historique APPEND-ONLY des corrections de notes verrouillées (lot L1).

    Contrairement à `NotificationModificationNote` (notification éphémère), ce
    modèle est la piste d'audit immuable : aucune vue/administration ne permet
    de le modifier ou de le supprimer. Chaque correction conserve l'ancienne et
    la nouvelle valeur ainsi que le motif obligatoire.
    """

    note = models.ForeignKey(
        NoteModule,
        on_delete=models.CASCADE,
        related_name='corrections',
    )
    colonne = models.ForeignKey(
        NoteModuleColonne,
        on_delete=models.CASCADE,
        related_name='corrections',
    )
    module = models.ForeignKey(
        Module,
        on_delete=models.CASCADE,
        related_name='corrections_notes',
    )
    participant = models.ForeignKey(
        Participant,
        on_delete=models.CASCADE,
        related_name='corrections_notes_modules',
    )
    ancienne_valeur = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    nouvelle_valeur = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    motif = models.TextField(help_text='Motif obligatoire de la correction.')
    auteur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='corrections_notes_modules',
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = 'Correction de note module'
        verbose_name_plural = 'Corrections de notes modules'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['module', 'created_at']),
            models.Index(fields=['colonne', 'participant']),
        ]

    def __str__(self):
        return (
            f'Correction {self.ancienne_valeur} → {self.nouvelle_valeur} '
            f'({self.motif[:40]}…)'
        )


class NotificationModificationNote(models.Model):
    """Notification in-app à la Direction lorsqu'un admin modifie une note déjà enregistrée."""

    destinataire = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications_modification_note',
    )
    auteur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notifications_modification_note_emises',
    )
    participant = models.ForeignKey(
        Participant,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notifications_modification_note',
    )
    module = models.ForeignKey(
        Module,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notifications_modification_note',
    )
    colonne_libelle = models.CharField(max_length=120, blank=True, default='')
    ancienne_note = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    nouvelle_note = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    message = models.TextField()
    lu = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Notification modification de note'
        verbose_name_plural = 'Notifications modifications de notes'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.message[:60]}… → {self.destinataire}'


class NotificationFinanceAjustement(models.Model):
    """Notification in-app pour le workflow ajustements horaires (Finance ↔ Direction)."""

    class Evenement(models.TextChoices):
        PROPOSE = 'PROPOSE', 'Ajustement proposé'
        VALIDE = 'VALIDE', 'Ajustement validé'
        REJETE = 'REJETE', 'Ajustement rejeté'

    destinataire = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications_finance_ajustement',
    )
    auteur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notifications_finance_ajustement_emises',
    )
    ajustement = models.ForeignKey(
        FinanceAjustement,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notifications',
    )
    evenement = models.CharField(max_length=20, choices=Evenement.choices)
    message = models.TextField()
    lu = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Notification ajustement finance'
        verbose_name_plural = 'Notifications ajustements finance'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.get_evenement_display()} → {self.destinataire}'
