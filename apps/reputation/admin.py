from django.contrib import admin
from .models import Deal, TrustScoreSettings


@admin.register(Deal)
class DealAdmin(admin.ModelAdmin):
    list_display = ('post', 'initiator', 'counterparty', 'status', 'created_at', 'confirmed_at')
    list_filter = ('status',)
    search_fields = ('post__title',)


@admin.register(TrustScoreSettings)
class TrustScoreSettingsAdmin(admin.ModelAdmin):
    list_display = ('neutral_rating', 'neutral_weight', 'min_reviews_to_display')

    def has_add_permission(self, request):
        return not TrustScoreSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
