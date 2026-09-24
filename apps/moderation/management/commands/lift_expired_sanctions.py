"""CDC 5.6 (complément Sprint 4) : lève automatiquement les suspensions
temporaires arrivées à échéance (ends_at dépassé). Tâche quotidienne."""
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.moderation.models import AuditLog, Sanction


class Command(BaseCommand):
    help = "Lève les suspensions temporaires arrivées à échéance."

    def handle(self, *args, **options):
        queryset = Sanction.objects.filter(
            sanction_type=Sanction.TYPE_SUSPENSION_TEMPORAIRE,
            is_active=True,
            ends_at__lt=timezone.now(),
        )
        count = 0
        for sanction in queryset:
            sanction.lift()
            AuditLog.record(actor=None, action='SANCTION_AUTO_LIFTED', target=sanction)
            count += 1

        if options['verbosity'] > 0:
            self.stdout.write(self.style.SUCCESS(f"{count} suspension(s) temporaire(s) levée(s) automatiquement."))
