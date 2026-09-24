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


@receiver(post_save, sender=Review)
def on_review_saved(sender, instance, **kwargs):
    _handle_review_change(instance)


@receiver(post_delete, sender=Review)
def on_review_deleted(sender, instance, **kwargs):
    _handle_review_change(instance)
