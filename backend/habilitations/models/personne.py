"""Modèle ``Personne`` : identité métier unique, distincte du compte.

Une personne porte l'identité civile et les rattachements institutionnels ;
le compte d'authentification (``authentication.User``) reste séparé et lui
est relié par :class:`habilitations.models.compte.CompteUtilisateur`.

Les liens vers les identités déjà présentes dans les applications métier
sont **nullables et non exclusifs** : une même personne peut être à la fois
un agent RH et un formateur vacataire. Ce sont des ``OneToOneField`` pour
qu'une identité source ne soit rattachée qu'à une seule :class:`Personne`,
en ``SET_NULL`` pour préserver la personne si l'enregistrement source est
supprimé un jour (les applications existantes ne sont pas modifiées).
"""
from django.db import models

from .enums import SituationPersonne


class Personne(models.Model):
    class Sexe(models.TextChoices):
        MASCULIN = 'M', 'Masculin'
        FEMININ = 'F', 'Féminin'
        AUTRE = '', 'Non renseigné'

    class Statut(models.TextChoices):
        ACTIF = 'ACTIF', 'Relation active avec l’INJS'
        SUSPENDU = 'SUSPENDU', 'Suspendue'
        PARTI = 'PARTI', 'Relation terminée'
        AUTRE = 'AUTRE', 'Autre situation'

    class TypePiece(models.TextChoices):
        CNI = 'CNI', 'Carte nationale d’identité'
        PASSEPORT = 'PASSEPORT', 'Passeport'
        ATTESTATION = 'ATTESTATION', 'Attestation d’identité'
        AUTRE = 'AUTRE', 'Autre document'

    # Identifiant institutionnel lisible (ex. PERS-2026-00001), unique.
    matricule = models.CharField(max_length=40, unique=True, db_index=True)

    civilite = models.CharField(max_length=10, blank=True)
    nom = models.CharField(max_length=120, db_index=True)
    prenoms = models.CharField(max_length=200, blank=True)
    nom_usage = models.CharField(max_length=120, blank=True)

    date_naissance = models.DateField(null=True, blank=True)
    lieu_naissance = models.CharField(max_length=150, blank=True, default='')
    sexe = models.CharField(max_length=2, choices=Sexe.choices, blank=True, default='')
    nationalite = models.CharField(max_length=80, blank=True, default='')

    telephone = models.CharField(max_length=30, blank=True, default='')
    telephone2 = models.CharField(max_length=30, blank=True, default='')
    email_personnel = models.EmailField(blank=True, default='')
    email_institutionnel = models.EmailField(blank=True, default='')

    photo = models.ImageField(upload_to='habilitations/personnes/', blank=True, null=True)

    piece_type = models.CharField(max_length=20, choices=TypePiece.choices,
                                  blank=True, default='')
    piece_numero = models.CharField(max_length=80, blank=True, default='')
    piece_echeance = models.DateField(null=True, blank=True)

    situation = models.CharField(
        max_length=20, choices=SituationPersonne.choices,
        default=SituationPersonne.EXTERNE,
    )
    # Rattachement en texte libre (les modèles Service/Direction varient selon
    # les apps ; la normalisation fine interviendra lors du rapprochement U8).
    service = models.CharField(max_length=150, blank=True, default='')
    direction = models.CharField(max_length=150, blank=True, default='')
    statut = models.CharField(max_length=20, choices=Statut.choices,
                              default=Statut.ACTIF)
    date_entree = models.DateField(null=True, blank=True)
    date_sortie = models.DateField(null=True, blank=True)

    # Liens non exclusifs vers les identités métier existantes.
    agent_rh = models.OneToOneField(
        'ressources_humaines.Agent', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='personne_habilitation',
    )
    formateur = models.OneToOneField(
        'formations.Formateur', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='personne_habilitation',
    )
    participant = models.OneToOneField(
        'formations.Participant', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='personne_habilitation',
    )
    dossier_etudiant = models.OneToOneField(
        'scolarite.DossierEtudiant', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='personne_habilitation',
    )
    candidat = models.OneToOneField(
        'admissions.Candidat', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='personne_habilitation',
    )

    notes = models.TextField(blank=True, default='')
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Personne'
        verbose_name_plural = 'Personnes'
        ordering = ('nom', 'prenoms')
        indexes = [
            models.Index(fields=['nom', 'date_naissance']),
            models.Index(fields=['email_institutionnel']),
        ]

    def __str__(self):
        return f'{self.matricule} · {self.nom} {self.prenoms}'.strip()

    @property
    def nom_complet(self):
        base = f'{self.prenoms} {self.nom}'.strip()
        return self.nom_usage or base or self.matricule
