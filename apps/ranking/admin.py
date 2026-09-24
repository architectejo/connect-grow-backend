from django.contrib import admin
from .models import RankingSettings


@admin.register(RankingSettings)
class RankingSettingsAdmin(admin.ModelAdmin):
    list_display = (
        'weight_views', 'weight_likes', 'weight_comments', 'weight_shares',
        'trust_factor_min', 'trust_factor_max', 'recency_half_life_hours',
    )

    def has_add_permission(self, request):
        # Singleton : une seule ligne de paramètres.
        return not RankingSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
