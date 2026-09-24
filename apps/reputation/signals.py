"""CDC 3.7 / 3.8 : le Trust Score d'un utilisateur est recalculé à chaque avis
créé, modifié ou retiré, puis répercuté sur le visibility_score de toutes ses
annonces actives (facteur T de l'algorithme Trust & Engage).

Importé depuis ReputationConfig.ready(), donc après le chargement complet du
registre des applications : les imports directs de modèles d'autres apps sont
sûrs ici (pas de risque d'import circulaire au chargement des modules)."""
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.interactions.models import Review

from .models import TrustScoreSettings


def recompute_trust_score(user):
    settings_row = TrustScoreSettings.get_solo()
    ratings = list(
        Review.objects.filter(reviewed_user=user, is_hidden=False).values_list('rating', flat=True)
    )
    n = len(ratings)
    trust_score = (settings_row.neutral_weight * settings_row.neutral_rating + sum(ratings)) / (
        settings_row.neutral_weight + n
    )

    user.trust_score = round(trust_score, 2)
    user.reviews_count = n
    user.save(update_fields=['trust_score', 'reviews_count'])

    from apps.marketplace.models import Post

    for post in Post.objects.filter(seller=user, is_active=True, is_delete=False):
        post.update_visibility_score()


def _handle_review_change(instance):
    if instance.reviewed_user_id:
        recompute_trust_score(instance.reviewed_user)


def check_crossed_reviews(review):
    """CDC 3.7 (anti-abus) : détecte les avis croisés répétés entre les deux
    mêmes comptes et les envoie en modération plutôt que de les bloquer —
    un faux positif ne doit pas empêcher un vrai avis d'exister."""
    from datetime import timedelta

    from django.contrib.contenttypes.models import ContentType
    from django.db.models import Q
    from django.utils import timezone

    from apps.moderation.models import Report

    user_a, user_b = review.user_id, review.reviewed_user_id
    if not user_a or not user_b:
        return

    thirty_days_ago = timezone.now() - timedelta(days=30)
    deal_ids = set(
        Review.objects.filter(
            Q(user_id=user_a, reviewed_user_id=user_b) | Q(user_id=user_b, reviewed_user_id=user_a),
            created_at__gte=thirty_days_ago,
        ).values_list('deal_id', flat=True)
    )

    if len(deal_ids) >= 3:
        content_type = ContentType.objects.get_for_model(Review)
        already_reported = Report.objects.filter(
            content_type=content_type, object_id=review.id, reason=Report.REASON_AVIS_CROISES,
        ).exists()
        if not already_reported:
            Report.objects.create(
                content_type=content_type,
                object_id=review.id,
                reporter=None,
                reason=Report.REASON_AVIS_CROISES,
                description=(
                    f"Avis croisés répétés détectés entre les utilisateurs {user_a} et {user_b} "
                    f"({len(deal_ids)} affaires distinctes sur 30 jours)."
                ),
            )


@receiver(post_save, sender=Review)
def on_review_saved(sender, instance, created, **kwargs):
    _handle_review_change(instance)
    if created:
        check_crossed_reviews(instance)


@receiver(post_delete, sender=Review)
def on_review_deleted(sender, instance, **kwargs):
    _handle_review_change(instance)
