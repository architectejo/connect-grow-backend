"""CDC 3.2 / 3.6 / 5.6 : expiration des annonces après N jours sans
renouvellement (tâche quotidienne), et notification « bientôt expirée »
quelques jours avant l'échéance."""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.interactions.models import Notification
from apps.marketplace.models import MarketplaceSettings, Post


class Command(BaseCommand):
    help = "Expire les annonces actives dépassant leur date d'expiration et notifie les échéances proches (CDC 3.2, 3.6)."

    def handle(self, *args, **options):
        now = timezone.now()
        settings_row = MarketplaceSettings.get_solo()

        expired = Post.objects.filter(status=Post.STATUS_ACTIVE, is_delete=False, expires_at__lt=now)
        expired_count = expired.update(status=Post.STATUS_EXPIRED, is_active=False)

        warning_cutoff = now + timedelta(days=settings_row.expiring_soon_warning_days)
        soon_expiring = Post.objects.filter(
            status=Post.STATUS_ACTIVE, is_delete=False,
            expires_at__gte=now, expires_at__lte=warning_cutoff,
            expiring_soon_notified=False,
        )
        notified_count = 0
        for post in soon_expiring:
            Notification.objects.create(
                user=post.seller,
                notification_type='EXPIRATION',
                title="Votre annonce expire bientôt",
                content=f"« {post.title} » expire le {post.expires_at:%d/%m/%Y}. Renouvelez-la pour rester visible.",
                link=f"/post/{post.id}",
            )
            post.expiring_soon_notified = True
            post.save(update_fields=['expiring_soon_notified'])
            notified_count += 1

        if options['verbosity'] > 0:
            self.stdout.write(self.style.SUCCESS(
                f"{expired_count} annonce(s) expirée(s), {notified_count} notification(s) d'échéance envoyée(s)."
            ))
