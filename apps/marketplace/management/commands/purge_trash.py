"""CDC 3.10 / 5.6 : purge automatique de la corbeille (annonces supprimées
depuis plus de 30 jours), tâche quotidienne. Les avis et les conversations
liées restent en base (Review.post et Deal.post sont en SET_NULL)."""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.marketplace.models import MarketplaceSettings, Post


class Command(BaseCommand):
    help = "Supprime définitivement les annonces en corbeille depuis plus de N jours (CDC 3.10)."

    def handle(self, *args, **options):
        retention_days = MarketplaceSettings.get_solo().trash_retention_days
        cutoff = timezone.now() - timedelta(days=retention_days)

        queryset = Post.objects.filter(is_delete=True, deleted_at__lt=cutoff)
        count = queryset.count()
        queryset.delete()

        if options['verbosity'] > 0:
            self.stdout.write(self.style.SUCCESS(f"{count} annonce(s) purgée(s) définitivement."))
