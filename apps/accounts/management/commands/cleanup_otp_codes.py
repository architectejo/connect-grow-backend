"""CDC 5.6 : suppression des OTP expirés, tâche horaire."""
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.models import OtpCode


class Command(BaseCommand):
    help = "Supprime les codes OTP expirés (CDC 5.6)."

    def handle(self, *args, **options):
        queryset = OtpCode.objects.filter(expires_at__lt=timezone.now())
        count = queryset.count()
        queryset.delete()

        if options['verbosity'] > 0:
            self.stdout.write(self.style.SUCCESS(f"{count} code(s) OTP expiré(s) supprimé(s)."))
