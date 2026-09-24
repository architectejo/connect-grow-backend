from django.db import migrations


def backfill_trust_scores(apps, schema_editor):
    """Calcule le Trust Score (moyenne bayésienne, CDC 3.7) de chaque utilisateur
    ayant déjà reçu des avis, avec les mêmes constantes par défaut que
    TrustScoreSettings (m=3.5, C=5) — cette ligne de paramètres n'existe pas
    forcément encore, donc les valeurs sont reprises ici explicitement plutôt
    que lues dessus."""
    Review = apps.get_model('interactions', 'Review')
    User = apps.get_model('accounts', 'User')

    neutral_rating, neutral_weight = 3.5, 5.0

    reviewed_user_ids = (
        Review.objects.filter(reviewed_user__isnull=False, is_hidden=False)
        .values_list('reviewed_user_id', flat=True)
        .distinct()
    )
    for user_id in reviewed_user_ids:
        ratings = list(
            Review.objects.filter(reviewed_user_id=user_id, is_hidden=False).values_list('rating', flat=True)
        )
        n = len(ratings)
        trust_score = (neutral_weight * neutral_rating + sum(ratings)) / (neutral_weight + n)
        User.objects.filter(pk=user_id).update(trust_score=round(trust_score, 2), reviews_count=n)


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0007_user_reviews_count_user_trust_score'),
        ('interactions', '0007_alter_review_unique_together_review_deal_and_more'),
        ('reputation', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(backfill_trust_scores, migrations.RunPython.noop),
    ]
