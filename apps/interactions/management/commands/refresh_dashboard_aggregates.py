"""CDC 5.6 : agrégats du dashboard (contacts reçus par annonce), tâche
horaire — même principe que le suivi des vues (marketplace.PostViewStat),
qui lui est déjà tenu à jour en temps réel."""
from django.core.management.base import BaseCommand
from django.db.models import Count
from django.utils import timezone

from apps.interactions.models import ContactRequest, ContactStat


class Command(BaseCommand):
    help = "Recalcule l'agrégat quotidien des contacts reçus par annonce (CDC 3.9, 5.6)."

    def handle(self, *args, **options):
        today = timezone.now().date()
        counts = (
            ContactRequest.objects.filter(created_at__date=today)
            .values('post_id', 'post__seller_id')
            .annotate(total=Count('id'))
        )

        for row in counts:
            ContactStat.objects.update_or_create(
                post_id=row['post_id'], date=today,
                defaults={'seller_id': row['post__seller_id'], 'count': row['total']},
            )

        if options['verbosity'] > 0:
            self.stdout.write(self.style.SUCCESS(f"Agrégat de contacts recalculé pour {len(counts)} annonce(s)."))
