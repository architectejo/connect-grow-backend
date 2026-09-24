from django.conf import settings
from django.db import models
from django.utils import timezone


class TrustScoreSettings(models.Model):
    """CDC 3.7 : paramètres de la moyenne bayésienne du Trust Score,
    modifiables dans le back-office. Ligne singleton (pk=1)."""

    neutral_rating = models.FloatField(default=3.5, help_text="m : note neutre")
    neutral_weight = models.FloatField(default=5.0, help_text="C : poids de la note neutre")
    min_reviews_to_display = models.PositiveIntegerField(default=3)

    class Meta:
        verbose_name = "Paramètres du Trust Score"
        verbose_name_plural = "Paramètres du Trust Score"

    def __str__(self):
        return "Paramètres du Trust Score"

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class Deal(models.Model):
    """CDC 3.7 : « affaire conclue » — interaction déclarée par l'une des
    parties et confirmée par l'autre, seule condition d'accès au droit d'avis.
    Au MVP, déclarée depuis l'historique des contacts (apps.interactions)."""

    STATUS_PENDING = 'PENDING'
    STATUS_CONFIRMED = 'CONFIRMED'
    STATUS_DECLINED = 'DECLINED'
    STATUS_CHOICES = (
        (STATUS_PENDING, "En attente de confirmation"),
        (STATUS_CONFIRMED, "Confirmée"),
        (STATUS_DECLINED, "Refusée"),
    )

    post = models.ForeignKey('marketplace.Post', on_delete=models.CASCADE, related_name='deals')
    initiator = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='deals_initiated',
    )
    counterparty = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='deals_to_confirm',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def other_party(self, user):
        if self.initiator_id == user.id:
            return self.counterparty
        if self.counterparty_id == user.id:
            return self.initiator
        return None

    def confirm(self):
        self.status = self.STATUS_CONFIRMED
        self.confirmed_at = timezone.now()
        self.save(update_fields=['status', 'confirmed_at'])

    def decline(self):
        self.status = self.STATUS_DECLINED
        self.save(update_fields=['status'])

    def __str__(self):
        return f"Affaire {self.post.title} ({self.get_status_display()})"
