from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone


class Report(models.Model):
    """CDC 3.11 : file unique de signalements (annonces, avis, messages,
    utilisateurs). Un seul modèle polymorphe via content types plutôt qu'une
    table par type de cible signalée."""

    REASON_SPAM = 'SPAM'
    REASON_ARNAQUE = 'ARNAQUE'
    REASON_CONTENU_INTERDIT = 'CONTENU_INTERDIT'
    REASON_HARCELEMENT = 'HARCELEMENT'
    REASON_AVIS_CROISES = 'AVIS_CROISES'
    REASON_AUTRE = 'AUTRE'
    REASON_CHOICES = (
        (REASON_SPAM, "Spam"),
        (REASON_ARNAQUE, "Arnaque"),
        (REASON_CONTENU_INTERDIT, "Contenu interdit"),
        (REASON_HARCELEMENT, "Harcèlement"),
        (REASON_AVIS_CROISES, "Avis croisés suspects"),
        (REASON_AUTRE, "Autre"),
    )

    STATUS_EN_ATTENTE = 'EN_ATTENTE'
    STATUS_EN_COURS = 'EN_COURS'
    STATUS_TRAITE = 'TRAITE'
    STATUS_REJETE = 'REJETE'
    STATUS_CHOICES = (
        (STATUS_EN_ATTENTE, "En attente"),
        (STATUS_EN_COURS, "Prise en charge"),
        (STATUS_TRAITE, "Traité"),
        (STATUS_REJETE, "Rejeté"),
    )

    # La cible signalée : une annonce, un avis, un message ou un utilisateur.
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    target = GenericForeignKey('content_type', 'object_id')

    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='reports_filed',
    )
    reason = models.CharField(max_length=20, choices=REASON_CHOICES)
    description = models.TextField(blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_EN_ATTENTE)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='reports_assigned',
    )
    decision_notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['content_type', 'object_id'])]

    def claim(self, moderator):
        self.status = self.STATUS_EN_COURS
        self.assigned_to = moderator
        self.save(update_fields=['status', 'assigned_to'])

    def resolve(self, notes=''):
        self.status = self.STATUS_TRAITE
        self.decision_notes = notes
        self.resolved_at = timezone.now()
        self.save(update_fields=['status', 'decision_notes', 'resolved_at'])

    def reject(self, notes=''):
        self.status = self.STATUS_REJETE
        self.decision_notes = notes
        self.resolved_at = timezone.now()
        self.save(update_fields=['status', 'decision_notes', 'resolved_at'])

    def __str__(self):
        return f"Signalement #{self.id} ({self.get_reason_display()}) — {self.get_status_display()}"


class Sanction(models.Model):
    """CDC 3.11 : avertissement, masquage d'une annonce, suspension
    temporaire, bannissement."""

    TYPE_AVERTISSEMENT = 'AVERTISSEMENT'
    TYPE_MASQUAGE_ANNONCE = 'MASQUAGE_ANNONCE'
    TYPE_SUSPENSION_TEMPORAIRE = 'SUSPENSION_TEMPORAIRE'
    TYPE_BANNISSEMENT = 'BANNISSEMENT'
    TYPE_CHOICES = (
        (TYPE_AVERTISSEMENT, "Avertissement"),
        (TYPE_MASQUAGE_ANNONCE, "Masquage d'une annonce"),
        (TYPE_SUSPENSION_TEMPORAIRE, "Suspension temporaire"),
        (TYPE_BANNISSEMENT, "Bannissement"),
    )

    # Rôles autorisés à prononcer chaque type de sanction (CDC 3.11 : « chaque
    # rôle n'accède qu'aux modules qui le concernent »). Un modérateur peut
    # avertir ou masquer une annonce ; seul un administrateur (ou plus) peut
    # suspendre ou bannir.
    MODERATOR_ALLOWED_TYPES = (TYPE_AVERTISSEMENT, TYPE_MASQUAGE_ANNONCE)

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sanctions')
    sanction_type = models.CharField(max_length=30, choices=TYPE_CHOICES)
    reason = models.TextField()
    related_post = models.ForeignKey(
        'marketplace.Post', on_delete=models.SET_NULL, null=True, blank=True, related_name='sanctions',
    )
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='sanctions_issued',
    )

    is_active = models.BooleanField(default=True)
    starts_at = models.DateTimeField(auto_now_add=True)
    # CDC 5.6 : la levée automatique à ends_at est une tâche planifiée (Sprint 5) ;
    # d'ici là, seule une levée manuelle (lift()) est possible.
    ends_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def apply(self):
        if self.sanction_type == self.TYPE_MASQUAGE_ANNONCE and self.related_post_id:
            self.related_post.is_active = False
            self.related_post.save(update_fields=['is_active'])
        elif self.sanction_type in (self.TYPE_SUSPENSION_TEMPORAIRE, self.TYPE_BANNISSEMENT):
            self.user.is_active = False
            self.user.save(update_fields=['is_active'])

    def lift(self):
        if self.sanction_type == self.TYPE_MASQUAGE_ANNONCE and self.related_post_id:
            self.related_post.is_active = True
            self.related_post.save(update_fields=['is_active'])
        elif self.sanction_type in (self.TYPE_SUSPENSION_TEMPORAIRE, self.TYPE_BANNISSEMENT):
            self.user.is_active = True
            self.user.save(update_fields=['is_active'])
        self.is_active = False
        self.save(update_fields=['is_active'])

    def __str__(self):
        return f"{self.get_sanction_type_display()} — {self.user}"


class ForbiddenItem(models.Model):
    """CDC 2.1 / 3.11 : liste des produits et services interdits, référentiel
    consulté par la modération (médicaments, armes, contrefaçons...)."""

    keyword = models.CharField(max_length=100, unique=True)
    category = models.ForeignKey(
        'marketplace.Category', on_delete=models.SET_NULL, null=True, blank=True, related_name='forbidden_items',
    )
    added_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['keyword']

    def __str__(self):
        return self.keyword


class AuditLog(models.Model):
    """CDC 3.11 : journal horodaté de toutes les actions des modérateurs et
    administrateurs."""

    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=50)
    content_type = models.ForeignKey(ContentType, on_delete=models.SET_NULL, null=True, blank=True)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    target = GenericForeignKey('content_type', 'object_id')
    details = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    @classmethod
    def record(cls, actor, action, target=None, details=''):
        entry = cls(actor=actor, action=action, details=details)
        if target is not None:
            entry.content_type = ContentType.objects.get_for_model(target)
            entry.object_id = target.pk
        entry.save()
        return entry

    def __str__(self):
        return f"{self.action} par {self.actor} le {self.created_at:%Y-%m-%d %H:%M}"
