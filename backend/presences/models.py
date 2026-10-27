from django.conf import settings
from django.db import models
from django.utils import timezone
from formations.models import Participant, Formateur, SessionModule
from config.client_ip import get_client_ip


class Pointage(models.Model):
    class Statut(models.TextChoices):
        EN_COURS = 'EN_COURS', 'En cours (en salle)'
        TERMINE = 'TERMINE', 'Terminé'
        FORCE_DFRC = 'FORCE_DFRC', 'Forcé par DFRC'
        ABSENT_NON_BADGE = 'ABSENT_NON_BADGE', 'Absent (non badgé à la sortie)'
        HORS_LIGNE_SUSPECT = 'HORS_LIGNE_SUSPECT', 'Hors ligne suspect'
        SORTIE_AUTO = 'SORTIE_AUTO', 'Sortie automatique (anti-fraude)'

    participant = models.ForeignKey(
        Participant,
        on_delete=models.CASCADE,
        related_name='pointages',
        null=True,
        blank=True,
    )
    formateur = models.ForeignKey(
        Formateur,
        on_delete=models.CASCADE,
        related_name='pointages',
        null=True,
        blank=True,
    )
    encadrant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='pointages_encadrant',
        null=True,
        blank=True,
        limit_choices_to={'role': 'ENCADRANT'},
    )
    session = models.ForeignKey(
        SessionModule,
        on_delete=models.CASCADE,
        related_name='pointages',
        null=True,
        blank=True,
        help_text="Séance liée à ce pointage (null pour une séance LMD badgée via QR EDT)",
    )
    # Lot C refonte — séance LMD badgée via le QR des créneaux d'EDT
    # (empilement avec le badgeage legacy ; les pointages existants gardent
    # leur séance d'origine).
    seance_edt = models.ForeignKey(
        'edts.AffectationCreneau',
        on_delete=models.CASCADE,
        related_name='pointages',
        null=True,
        blank=True,
    )
    date_journee = models.DateField(default=timezone.localdate)
    device_id = models.CharField(max_length=255, blank=True, default='')
    last_heartbeat_at = models.DateTimeField(null=True, blank=True)
    last_latitude = models.FloatField(null=True, blank=True)
    last_longitude = models.FloatField(null=True, blank=True)
    last_accuracy_m = models.FloatField(null=True, blank=True)
    last_battery_level = models.PositiveSmallIntegerField(null=True, blank=True)
    last_is_charging = models.BooleanField(null=True, blank=True)
    outside_geofence_count = models.PositiveSmallIntegerField(default=0)
    timestamp_entree = models.DateTimeField()
    timestamp_sortie = models.DateTimeField(null=True, blank=True)
    duree_presence_minutes = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True,
    )
    statut = models.CharField(
        max_length=20,
        choices=Statut.choices,
        default=Statut.EN_COURS,
    )
    # Lot L1 - assiduite (alignee sur le referentiel demande). Les 6 statuts
    # ci-dessus decrivent le PROCESSUS de badgeage ; le statut d'assiduite
    # ci-dessous decrit le RESULTAT pedagogique (mapping explicite, aucun
    # statut existant renomme ni supprime, historique preserve).
    class StatutAssiduite(models.TextChoices):
        PRESENT = 'PRESENT', 'Present'
        ABSENT = 'ABSENT', 'Absent'
        RETARD = 'RETARD', 'Retard'
        ABSENCE_JUSTIFIEE = 'ABSENCE_JUSTIFIEE', 'Absence justifiee'
        EXCUSE = 'EXCUSE', 'Excuse'
        NON_RENSEIGNE = 'NON_RENSEIGNE', 'Non renseigne'

    statut_assiduite = models.CharField(
        max_length=20,
        choices=StatutAssiduite.choices,
        null=True,
        blank=True,
        help_text=(
            "Statut d'assiduité pédagogique. Null = non renseigné. "
            "Mapping depuis le statut de processus : voir MAPPING_ASSIDUITE."
        ),
    )
    annee_academique = models.ForeignKey(
        'scolarite.AnneeAcademique',
        on_delete=models.SET_NULL,
        related_name='pointages_lmd',
        null=True,
        blank=True,
        help_text="Année académique LMD (déduite de l'inscription de l'étudiant).",
    )
    groupe_lmd = models.ForeignKey(
        'scolarite.Groupe',
        on_delete=models.SET_NULL,
        related_name='pointages_lmd',
        null=True,
        blank=True,
        help_text="Groupe LMD (scolarite.Groupe) de l'étudiant pour cette séance.",
    )
    ecue_lmd = models.ForeignKey(
        'scolarite.ECUE',
        on_delete=models.SET_NULL,
        related_name='pointages_lmd',
        null=True,
        blank=True,
        help_text="ECUE via la passerelle Module.ref_module (chaîne LMD).",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date_journee', '-timestamp_entree']
        verbose_name = 'Pointage'
        verbose_name_plural = 'Pointages'
        indexes = [
            models.Index(fields=['date_journee', 'session'], name='pointage_date_session_idx'),
            models.Index(fields=['session', 'participant'], name='pointage_session_part_idx'),
            models.Index(fields=['session', 'formateur'], name='pointage_session_form_idx'),
            models.Index(fields=['session', 'encadrant'], name='pointage_session_enc_idx'),
            models.Index(fields=['participant', 'date_journee'], name='pointage_part_date_idx'),
            models.Index(fields=['statut', 'timestamp_sortie'], name='pointage_statut_sortie_idx'),
        ]

    @classmethod
    def MAPPING_ASSIDUITE(cls):
        """Mapping explicite statut de processus -> statut d'assiduite (lot L1).

        Principe : on ne qualifie une absence que lorsqu'elle est certaine ;
        les statuts suspects (HORS_LIGNE_SUSPECT) restent NON_RENSEIGNE tant
        qu'un agent n'a pas tranche manuellement.
        """
        return {
            cls.Statut.EN_COURS: cls.StatutAssiduite.PRESENT,
            cls.Statut.TERMINE: cls.StatutAssiduite.PRESENT,
            cls.Statut.FORCE_DFRC: cls.StatutAssiduite.PRESENT,
            cls.Statut.ABSENT_NON_BADGE: cls.StatutAssiduite.ABSENT,
            cls.Statut.HORS_LIGNE_SUSPECT: cls.StatutAssiduite.NON_RENSEIGNE,
            cls.Statut.SORTIE_AUTO: cls.StatutAssiduite.PRESENT,
        }

    def statut_assiduite_effectif(self):
        """Assiduite effective : champ manuel si renseigne, sinon mapping."""
        if self.statut_assiduite:
            return self.statut_assiduite
        return self.MAPPING_ASSIDUITE().get(self.statut, self.StatutAssiduite.NON_RENSEIGNE)

    def save(self, *args, **kwargs):
        """Lot L1 - audit de toute modification apres cloture de seance."""
        if self.pk:
            ancien = Pointage.objects.filter(pk=self.pk).first()
            seance_close = bool(
                (ancien and ancien.statut in (
                    self.Statut.TERMINE, self.Statut.ABSENT_NON_BADGE,
                    self.Statut.SORTIE_AUTO,
                )) or (self.session_id and self.session.terminee_le)
            )
            statut_change = ancien and ancien.statut != self.statut
            if seance_close and statut_change:
                super().save(*args, **kwargs)
                try:
                    from scolarite.models import (
                        JournalScolarite, journaliser as journal_scolarite,
                    )

                    AuditLog.objects.create(
                        action=AuditLog.Action.POINTAGE_MODIFIE,
                        acteur=None,
                        acteur_label='systeme',
                        cible_type=self.type_personne,
                        cible_numero=getattr(self.personne, 'matricule', '') or '',
                        cible_nom=str(self.personne or '')[:255],
                        pointage=self,
                        extra={
                            'session_id': self.session_id,
                            'ancienne_valeur': ancien.statut,
                            'nouvelle_valeur': self.statut,
                        },
                    )
                    journal_scolarite(
                        JournalScolarite.Action.EVENEMENT_SCOLARITE,
                        objet=self,
                        ancienne_valeur=ancien.statut,
                        nouvelle_valeur=self.statut,
                        commentaire='Modification de présence après clôture',
                    )
                except Exception:  # noqa: BLE001 - audit best-effort
                    pass
                return
        super().save(*args, **kwargs)

    @property
    def personne(self):
        """Retourne la personne liée (participant, formateur ou encadrant)."""
        return self.participant or self.formateur or self.encadrant

    @property
    def type_personne(self):
        if self.formateur_id:
            return 'formateur'
        if self.encadrant_id:
            return 'encadrant'
        return 'participant'

    @property
    def formation(self):
        return self.session.module.formation

    def __str__(self):
        personne = self.personne
        return f"{personne} — {self.session.module.formation.formation} ({self.get_statut_display()})"

    def calculer_duree(self):
        """Calcule la durée de présence côté serveur (R5).

        Règle SYGEP unique : durée clampée au créneau planifié de la séance
        (voir ``presences.duree``), jamais négative.
        """
        from .duree import pointage_minutes_clampees

        if self.timestamp_entree and self.timestamp_sortie:
            self.duree_presence_minutes = pointage_minutes_clampees(self)
        return self.duree_presence_minutes


class AuditLog(models.Model):
    """Trace toutes les actions critiques du système (badgeage, force, fermeture session)."""

    class Action(models.TextChoices):
        # ── Badgeage ──
        SCAN_ENTREE = 'SCAN_ENTREE', 'Scan entrée (QR public)'
        SCAN_SORTIE = 'SCAN_SORTIE', 'Scan sortie (QR public)'
        SCAN_SECURE_ENTREE = 'SCAN_SECURE_ENTREE', 'Scan sécurisé entrée (mobile)'
        SCAN_SECURE_SORTIE = 'SCAN_SECURE_SORTIE', 'Scan sécurisé sortie (mobile)'
        FORCE_ENTREE = 'FORCE_ENTREE', 'Entrée forcée (encadrant/DFRC)'
        FORCE_SORTIE = 'FORCE_SORTIE', 'Sortie forcée (encadrant/DFRC)'
        CLOSE_SESSION = 'CLOSE_SESSION', 'Fermeture de session (encadrant/DFRC)'
        AUTO_ABSENT = 'AUTO_ABSENT', 'Absent automatique (délai badge sortie dépassé)'
        SCAN_HEARTBEAT = 'SCAN_HEARTBEAT', 'Heartbeat mobile géolocalisé'
        NO_HEARTBEAT = 'NO_HEARTBEAT', 'Alerte absence heartbeat mobile'
        OUT_OF_GEOFENCE = 'OUT_OF_GEOFENCE', 'Sortie du périmètre géographique'
        AUTO_EXIT = 'AUTO_EXIT', 'Sortie automatique (heartbeat/geofence)'
        DEVICE_UNBIND = 'DEVICE_UNBIND', 'Déliaison appareil'
        # ── Formations ──
        FORMATION_CREATE = 'FORMATION_CREATE', 'Création de formation'
        FORMATION_UPDATE = 'FORMATION_UPDATE', 'Modification de formation'
        FORMATION_DELETE = 'FORMATION_DELETE', 'Suppression de formation'
        FORMATION_STATUT = 'FORMATION_STATUT', 'Changement de statut de formation'
        FORMATION_ASSIGN_SUPERVISEUR = 'FORMATION_ASSIGN_SUPERVISEUR', 'Assignation superviseur'
        MODULE_ASSIGN_SUPERVISEUR = 'MODULE_ASSIGN_SUPERVISEUR', 'Assignation encadrant à un module'
        MODULE_CREATE = 'MODULE_CREATE', 'Création de module'
        MODULE_UPDATE = 'MODULE_UPDATE', 'Modification de module'
        MODULE_DELETE = 'MODULE_DELETE', 'Suppression de module'
        MODULE_ARCHIVE = 'MODULE_ARCHIVE', 'Archivage de module'
        MODULE_UNARCHIVE = 'MODULE_UNARCHIVE', 'Désarchivage de module'
        FORMATION_QR_GENERATE = 'FORMATION_QR_GENERATE', 'Génération QR code'
        # ── Séances ──
        SEANCE_CREATE = 'SEANCE_CREATE', 'Création de séance'
        SEANCE_START = 'SEANCE_START', 'Démarrage de séance'
        SEANCE_STOP = 'SEANCE_STOP', 'Arrêt de séance'
        SEANCE_UPDATE = 'SEANCE_UPDATE', 'Modification de séance'
        SEANCE_DELETE = 'SEANCE_DELETE', 'Suppression de séance'
        SEANCE_IMPORT = 'SEANCE_IMPORT', 'Import séances (Excel)'
        # ── Auditeurs ──
        PARTICIPANT_CREATE = 'PARTICIPANT_CREATE', 'Création d\'auditeur'
        PARTICIPANT_UPDATE = 'PARTICIPANT_UPDATE', 'Modification d\'auditeur'
        PARTICIPANT_DELETE = 'PARTICIPANT_DELETE', 'Suppression d\'auditeur'
        PARTICIPANT_ADD_FORMATION = 'PARTICIPANT_ADD_FORMATION', 'Inscription auditeur à formation'
        PARTICIPANT_REMOVE_FORMATION = 'PARTICIPANT_REMOVE_FORMATION', 'Désinscription auditeur de formation'
        PARTICIPANT_IMPORT = 'PARTICIPANT_IMPORT', 'Import auditeurs (Excel)'
        # ── Rattrapages (déplacement inter-cohorte) ──
        RATTRAPAGE_CREATE = 'RATTRAPAGE_CREATE', 'Création d\'un rattrapage inter-cohorte'
        RATTRAPAGE_PRESENCE = 'RATTRAPAGE_PRESENCE', 'Présence générée pour un rattrapage'
        RATTRAPAGE_CANCEL = 'RATTRAPAGE_CANCEL', 'Annulation d\'un rattrapage'
        # ── Formateurs ──
        FORMATEUR_CREATE = 'FORMATEUR_CREATE', 'Création de formateur'
        FORMATEUR_UPDATE = 'FORMATEUR_UPDATE', 'Modification de formateur'
        FORMATEUR_DELETE = 'FORMATEUR_DELETE', 'Suppression de formateur'
        FORMATEUR_ADD_FORMATION = 'FORMATEUR_ADD_FORMATION', 'Assignation formateur à formation'
        FORMATEUR_REMOVE_FORMATION = 'FORMATEUR_REMOVE_FORMATION', 'Retrait formateur de formation'
        FORMATEUR_IMPORT = 'FORMATEUR_IMPORT', 'Import formateurs (Excel)'
        # ── Utilisateurs ──
        USER_CREATE = 'USER_CREATE', 'Création d\'utilisateur'
        USER_UPDATE = 'USER_UPDATE', 'Modification d\'utilisateur'
        USER_DELETE = 'USER_DELETE', 'Suppression d\'utilisateur'
        USER_LOGIN = 'USER_LOGIN', 'Connexion utilisateur'
        USER_LOGOUT = 'USER_LOGOUT', 'Déconnexion utilisateur'
        USER_PASSWORD_CHANGE = 'USER_PASSWORD_CHANGE', 'Changement de mot de passe'
        # ── Secrétariats ──
        SECRETARIAT_CREATE = 'SECRETARIAT_CREATE', 'Création de secrétariat'
        SECRETARIAT_UPDATE = 'SECRETARIAT_UPDATE', 'Modification de secrétariat'
        SECRETARIAT_DELETE = 'SECRETARIAT_DELETE', 'Suppression de secrétariat'
        # ── Référentiels ──
        REFERENTIEL_CREATE = 'REFERENTIEL_CREATE', 'Création référentiel'
        REFERENTIEL_UPDATE = 'REFERENTIEL_UPDATE', 'Modification référentiel'
        REFERENTIEL_DELETE = 'REFERENTIEL_DELETE', 'Suppression référentiel'
        # ── Imports globaux ──
        IMPORT_EXCEL = 'IMPORT_EXCEL', 'Import Excel global'
        # ── Finance ──
        FINANCE_AJUSTEMENT_PROPOSE = 'FINANCE_AJUSTEMENT_PROPOSE', 'Proposition ajustement horaire finance'
        FINANCE_AJUSTEMENT_VALIDE = 'FINANCE_AJUSTEMENT_VALIDE', 'Validation ajustement horaire finance'
        FINANCE_AJUSTEMENT_REJETE = 'FINANCE_AJUSTEMENT_REJETE', 'Rejet ajustement horaire finance'
        FINANCE_SETTINGS_UPDATE = 'FINANCE_SETTINGS_UPDATE', 'Modification paramètres finance'
        # Lot L1 - presences
        POINTAGE_MODIFIE = 'POINTAGE_MODIFIE', 'Modification de presence apres cloture'
        # Lot L1 - notes (workflow de validation)
        NOTE_SOUMISE = 'NOTE_SOUMISE', 'Note soumise pour validation'
        NOTE_VALIDEE = 'NOTE_VALIDEE', 'Note validée et verrouillée'
        NOTE_CORRIGEE = 'NOTE_CORRIGEE', 'Correction de note verrouillée'

    action = models.CharField(max_length=40, choices=Action.choices)

    # Qui a déclenché l'action (null = scan public anonyme)
    acteur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_logs',
        help_text="Utilisateur connecté ayant réalisé l'action (null si scan public)",
    )
    acteur_label = models.CharField(
        max_length=255, blank=True, default='',
        help_text="Nom de l'acteur au moment de l'action (dénormalisé)",
    )

    # Sur qui porte l'action
    cible_type = models.CharField(
        max_length=20, blank=True, default='',
        help_text="'participant', 'formateur' ou 'encadrant'",
    )
    cible_numero = models.CharField(max_length=50, blank=True, default='')
    cible_nom = models.CharField(max_length=255, blank=True, default='')

    # Contexte
    formation = models.ForeignKey(
        'formations.Formation',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_logs',
    )
    formation_titre = models.CharField(max_length=255, blank=True, default='')
    pointage = models.ForeignKey(
        'Pointage',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_logs',
    )

    # Métadonnées
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    device_id = models.CharField(max_length=255, blank=True, default='')
    extra = models.JSONField(default=dict, blank=True, help_text="Données supplémentaires libres")

    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-timestamp']
        verbose_name = 'Journal d\'audit'
        verbose_name_plural = 'Journal d\'audit'
        indexes = [
            models.Index(fields=['action', 'timestamp']),
            models.Index(fields=['acteur', 'timestamp']),
            models.Index(fields=['cible_numero', 'timestamp']),
        ]

    def __str__(self):
        acteur = self.acteur_label or 'Anonyme'
        return f"[{self.get_action_display()}] {acteur} → {self.cible_nom} ({self.timestamp:%Y-%m-%d %H:%M})"


def _log_audit(
    action, request, cible_type='', cible_numero='', cible_nom='',
    formation=None, pointage=None, device_id='', extra=None,
):
    """Raccourci pour créer un AuditLog depuis une vue."""
    acteur = None
    acteur_label = ''
    if request and request.user and request.user.is_authenticated:
        acteur = request.user
        acteur_label = request.user.get_full_name() or request.user.username

    AuditLog.objects.create(
        action=action,
        acteur=acteur,
        acteur_label=acteur_label,
        cible_type=cible_type,
        cible_numero=cible_numero,
        cible_nom=cible_nom,
        formation=formation,
        formation_titre=formation.formation if formation else '',
        pointage=pointage,
        ip_address=get_client_ip(request) if request else None,
        device_id=device_id or '',
        extra=extra or {},
    )


def log_audit_system(action, *, formation=None, extra=None):
    """Journalise une action automatique (sans utilisateur connecté)."""
    AuditLog.objects.create(
        action=action,
        acteur=None,
        acteur_label='Système',
        formation=formation,
        formation_titre=formation.formation if formation else '',
        extra=extra or {},
    )


class DeviceBinding(models.Model):
    """Lie un appareil mobile à un utilisateur.
    Empêche qu'un participant se déconnecte et se reconnecte
    avec le compte d'un autre depuis le même téléphone."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='device_bindings',
    )
    device_id = models.CharField(max_length=255, unique=True, db_index=True)
    device_info = models.CharField(max_length=500, blank=True, default='')
    bound_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Liaison appareil'
        verbose_name_plural = 'Liaisons appareils'

    def __str__(self):
        return f"{self.user} ↔ {self.device_id[:20]}..."


class Rattrapage(models.Model):
    """Rattrapage d'un cours par un auditeur dans la séance d'une AUTRE cohorte.

    Un auditeur (groupe/grade/vague/secrétariat A) peut suivre le même cours
    dispensé à une autre cohorte (B) pour rattraper une séance manquée.

    Ce modèle trace explicitement l'opération SANS modifier l'appartenance de
    cohorte de l'auditeur ni créer d'inscription ``ModuleParticipant`` sur le
    module d'accueil : les effectifs attendus de la cohorte B ne sont donc pas
    pollués. La présence effective est un ``Pointage`` forcé, lié ici.
    """

    class Statut(models.TextChoices):
        PLANIFIE = 'PLANIFIE', 'Planifié'
        EFFECTUE = 'EFFECTUE', 'Effectué'
        ANNULE = 'ANNULE', 'Annulé'

    participant = models.ForeignKey(
        Participant,
        on_delete=models.CASCADE,
        related_name='rattrapages',
        help_text="Auditeur qui effectue le rattrapage",
    )
    seance_rattrapage = models.ForeignKey(
        SessionModule,
        on_delete=models.CASCADE,
        related_name='rattrapages',
        help_text="Séance d'accueil (autre cohorte) où l'auditeur rattrape le cours",
    )
    module_origine = models.ForeignKey(
        'formations.Module',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='rattrapages_origine',
        help_text="Module de la cohorte d'origine (cours manqué). Optionnel.",
    )
    seance_manquee = models.ForeignKey(
        SessionModule,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='rattrapages_manques',
        help_text="Séance précise manquée par l'auditeur. Optionnel.",
    )
    pointage = models.OneToOneField(
        'Pointage',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='rattrapage',
        help_text="Présence effectivement générée pour ce rattrapage",
    )
    statut = models.CharField(
        max_length=10,
        choices=Statut.choices,
        default=Statut.PLANIFIE,
        db_index=True,
    )
    motif = models.CharField(
        max_length=500,
        blank=True,
        default='',
        help_text="Motif du rattrapage (ex. absence justifiée, chevauchement…)",
    )
    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='rattrapages_crees',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Rattrapage'
        verbose_name_plural = 'Rattrapages'
        constraints = [
            models.UniqueConstraint(
                fields=['participant', 'seance_rattrapage'],
                name='uniq_rattrapage_participant_seance',
            ),
        ]
        indexes = [
            models.Index(fields=['participant', 'statut']),
            models.Index(fields=['seance_rattrapage', 'statut']),
        ]

    @property
    def module_rattrapage(self):
        return self.seance_rattrapage.module if self.seance_rattrapage_id else None

    @property
    def formation(self):
        module = self.module_rattrapage
        return module.formation if module else None

    def __str__(self):
        return (
            f"Rattrapage {self.participant} → {self.seance_rattrapage} "
            f"({self.get_statut_display()})"
        )



class NotificationAbsence(models.Model):
    """Lot L1 - notification in-app d'absence (seuil d'alerte depasse)."""

    destinataire = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications_absence',
        help_text="Destinataire (Direction / Secretariat).",
    )
    auteur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='notifications_absence_emises',
    )
    etudiant = models.ForeignKey(
        'scolarite.DossierEtudiant',
        on_delete=models.CASCADE,
        related_name='notifications_absence',
        null=True, blank=True,
    )
    session = models.ForeignKey(
        SessionModule,
        on_delete=models.SET_NULL,
        related_name='notifications_absence',
        null=True, blank=True,
    )
    # Lot C+ — l'alerte née d'une clôture de séance LMD référence la séance
    # d'origine (le flux legacy SessionModule reste sans seance_edt).
    seance_edt = models.ForeignKey(
        'edts.AffectationCreneau',
        on_delete=models.SET_NULL,
        related_name='notifications_absence',
        null=True, blank=True,
        verbose_name="Séance LMD",
        help_text="Séance d'origine de l'alerte (flux EDT/LMD uniquement).",
    )
    message = models.TextField()
    niveau = models.CharField(
        max_length=15,
        choices=[('AVERTISSEMENT', 'Avertissement'), ('CRITIQUE', 'Critique')],
        default='AVERTISSEMENT',
    )
    lue = models.BooleanField(default=False)
    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-cree_le']
        verbose_name = "Notification d'absence"
        verbose_name_plural = "Notifications d'absence"
        constraints = [
            models.UniqueConstraint(
                fields=('destinataire', 'etudiant', 'seance_edt', 'niveau'),
                condition=models.Q(seance_edt__isnull=False),
                name='notif_absence_lmd_non_dupliquee',
            ),
        ]

    def __str__(self):
        return f'[{self.niveau}] {self.message[:60]}'
