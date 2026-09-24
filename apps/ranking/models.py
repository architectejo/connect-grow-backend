from django.db import models


class RankingSettings(models.Model):
    """CDC 3.8 : pondérations, demi-vie et bornes de l'algorithme « Trust &
    Engage », paramétrables dans le back-office. Ligne singleton (pk=1)."""

    # Engagement E = 1 + ln(1 + w_views*vues + w_likes*likes + w_comments*commentaires + w_shares*partages)
    weight_views = models.FloatField(default=1.0)
    weight_likes = models.FloatField(default=3.0)
    weight_comments = models.FloatField(default=5.0)
    weight_shares = models.FloatField(default=8.0)

    # Confiance T = 0.8 + 0.4 * (TrustScore / 5), bornée à [trust_factor_min, trust_factor_max]
    trust_factor_min = models.FloatField(default=0.8)
    trust_factor_max = models.FloatField(default=1.2)

    # Récence R = e^(-λ * âge_heures), demi-vie en heures
    recency_half_life_hours = models.FloatField(default=72.0)

    class Meta:
        verbose_name = "Paramètres de classement"
        verbose_name_plural = "Paramètres de classement"

    def __str__(self):
        return "Paramètres de l'algorithme Trust & Engage"

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
