import io

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from PIL import Image
from rest_framework import status
from rest_framework.test import APITestCase

import math

from apps.accounts.models import User
from apps.ranking.models import RankingSettings
from .models import Category, City, Commune, Favorite, Post, PostImage, PostUniqueView, PostViewStat


def make_test_image(name='photo.jpg', color=(255, 0, 0), fmt='JPEG'):
    buffer = io.BytesIO()
    Image.new('RGB', (20, 20), color=color).save(buffer, format=fmt)
    buffer.seek(0)
    content_type = 'image/jpeg' if fmt == 'JPEG' else f'image/{fmt.lower()}'
    return SimpleUploadedFile(name, buffer.read(), content_type=content_type)


class MarketplaceTestBase(APITestCase):
    def setUp(self):
        self.city = City.objects.create(name='Kinshasa')
        self.commune = Commune.objects.create(city=self.city, name='Gombe')
        self.category = Category.objects.create(name='Électronique', slug='electronique')
        self.seller = User.objects.create_user(email='seller@example.com', password='x', full_name='Vendeur')
        self.buyer = User.objects.create_user(email='buyer@example.com', password='x', full_name='Acheteur')

    def make_post(self, **kwargs):
        defaults = dict(
            seller=self.seller,
            category=self.category,
            commune=self.commune,
            title='Un joli canapé à vendre',
            description='Description suffisamment longue pour passer la validation du CDC.',
            price=100,
            main_image=make_test_image(),
        )
        defaults.update(kwargs)
        return Post.objects.create(**defaults)


class WebpConversionTests(MarketplaceTestBase):
    def test_main_image_is_converted_to_webp_on_save(self):
        post = self.make_post()
        self.assertTrue(post.main_image.name.lower().endswith('.webp'))
        # Le fichier doit être un WebP valide, pas juste renommé.
        post.main_image.open()
        self.assertEqual(Image.open(post.main_image).format, 'WEBP')

    def test_gallery_image_is_converted_to_webp_on_save(self):
        post = self.make_post()
        image = PostImage.objects.create(post=post, image=make_test_image('extra.png', fmt='PNG'))
        self.assertTrue(image.image.name.lower().endswith('.webp'))


class PostValidationTests(MarketplaceTestBase):
    def test_title_shorter_than_ten_chars_is_rejected(self):
        self.client.force_authenticate(self.seller)
        response = self.client.post(reverse('post-list'), {
            'title': 'Trop court',
            'description': 'Description suffisamment longue pour la validation.',
            'category': self.category.id,
            'commune': self.commune.id,
            'price': 10,
            'main_image': make_test_image(),
        })
        # "Trop court" fait 10 caractères pile ; on force en dessous.
        response2 = self.client.post(reverse('post-list'), {
            'title': 'Court',
            'description': 'Description suffisamment longue pour la validation.',
            'category': self.category.id,
            'commune': self.commune.id,
            'price': 10,
            'main_image': make_test_image(),
        })
        self.assertEqual(response2.status_code, status.HTTP_400_BAD_REQUEST)

    def test_description_shorter_than_twenty_chars_is_rejected(self):
        self.client.force_authenticate(self.seller)
        response = self.client.post(reverse('post-list'), {
            'title': 'Un titre correct',
            'description': 'Trop court',
            'category': self.category.id,
            'commune': self.commune.id,
            'price': 10,
            'main_image': make_test_image(),
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class PostGalleryTests(MarketplaceTestBase):
    def test_owner_can_add_images_up_to_the_limit(self):
        post = self.make_post()
        self.client.force_authenticate(self.seller)
        # main_image compte pour 1 : il reste 7 places.
        for _ in range(7):
            PostImage.objects.create(post=post, image=make_test_image())
        response = self.client.post(
            reverse('post-images', args=[post.id]),
            {'image': make_test_image('one_too_many.jpg')},
            format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_non_owner_cannot_add_images(self):
        post = self.make_post()
        self.client.force_authenticate(self.buyer)
        response = self.client.post(
            reverse('post-images', args=[post.id]),
            {'image': make_test_image()},
            format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_owner_can_delete_a_gallery_image(self):
        post = self.make_post()
        image = PostImage.objects.create(post=post, image=make_test_image())
        self.client.force_authenticate(self.seller)
        response = self.client.delete(f"{reverse('post-images', args=[post.id])}?image_id={image.id}")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(PostImage.objects.filter(id=image.id).exists())


class FavoriteTests(MarketplaceTestBase):
    def test_toggle_favorite_adds_then_removes(self):
        post = self.make_post()
        self.client.force_authenticate(self.buyer)
        response = self.client.post(reverse('post-favorite', args=[post.id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['favorited'])
        self.assertTrue(Favorite.objects.filter(user=self.buyer, post=post).exists())

        response = self.client.post(reverse('post-favorite', args=[post.id]))
        self.assertFalse(response.data['favorited'])
        self.assertFalse(Favorite.objects.filter(user=self.buyer, post=post).exists())

    def test_favorites_list_only_shows_own_favorites(self):
        post = self.make_post()
        Favorite.objects.create(user=self.buyer, post=post)
        self.client.force_authenticate(self.seller)
        response = self.client.get(reverse('favorite-list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)

    def test_is_favorited_flag_on_post_detail(self):
        post = self.make_post()
        Favorite.objects.create(user=self.buyer, post=post)
        self.client.force_authenticate(self.buyer)
        response = self.client.get(reverse('post-detail', args=[post.id]))
        self.assertTrue(response.data['is_favorited'])


class PostFilterTests(MarketplaceTestBase):
    def setUp(self):
        super().setUp()
        self.cheap_usd = self.make_post(title='Chaise en bois massif', price=20, currency='USD')
        self.expensive_cdf = self.make_post(
            title='Téléviseur grand écran 4K', price=500000, currency='CDF', is_exchangeable=False,
        )

    def test_filter_by_currency(self):
        response = self.client.get(reverse('post-list'), {'currency': 'CDF'})
        ids = [p['id'] for p in response.data]
        self.assertIn(self.expensive_cdf.id, ids)
        self.assertNotIn(self.cheap_usd.id, ids)

    def test_filter_by_price_range(self):
        response = self.client.get(reverse('post-list'), {'price_min': 10, 'price_max': 100})
        ids = [p['id'] for p in response.data]
        self.assertIn(self.cheap_usd.id, ids)
        self.assertNotIn(self.expensive_cdf.id, ids)

    def test_filter_by_exchangeable(self):
        response = self.client.get(reverse('post-list'), {'is_exchangeable': 'false'})
        ids = [p['id'] for p in response.data]
        self.assertIn(self.expensive_cdf.id, ids)
        self.assertNotIn(self.cheap_usd.id, ids)


class SoftDeleteTests(MarketplaceTestBase):
    def test_soft_delete_sets_deleted_at(self):
        post = self.make_post()
        self.client.force_authenticate(self.seller)
        response = self.client.post(reverse('post-soft-delete', args=[post.id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        post.refresh_from_db()
        self.assertTrue(post.is_delete)
        self.assertIsNotNone(post.deleted_at)

    def test_restore_clears_deleted_at(self):
        post = self.make_post()
        self.client.force_authenticate(self.seller)
        self.client.post(reverse('post-soft-delete', args=[post.id]))
        self.client.post(reverse('post-restore', args=[post.id]))
        post.refresh_from_db()
        self.assertFalse(post.is_delete)
        self.assertIsNone(post.deleted_at)


class VisibilityScoreFormulaTests(MarketplaceTestBase):
    def test_formula_matches_cdc_spec(self):
        settings_row = RankingSettings.get_solo()
        post = self.make_post()
        post.views_count = 10
        post.likes_count = 2
        post.comments_count = 1
        post.shares_count = 0
        post.save(update_fields=['views_count', 'likes_count', 'comments_count', 'shares_count'])

        post.update_visibility_score()
        post.refresh_from_db()

        engagement_raw = (
            settings_row.weight_views * 10 + settings_row.weight_likes * 2 + settings_row.weight_comments * 1
        )
        expected_e = 1 + math.log(1 + engagement_raw)
        expected_t = 0.8 + 0.4 * (self.seller.trust_score / 5.0)
        age_hours = (post.last_score_update - post.created_at).total_seconds() / 3600
        expected_r = math.exp(-(math.log(2) / settings_row.recency_half_life_hours) * age_hours)
        expected = expected_e * expected_t * expected_r

        self.assertAlmostEqual(post.visibility_score, expected, places=6)

    def test_trust_factor_is_bounded(self):
        settings_row = RankingSettings.get_solo()
        post = self.make_post()
        self.seller.trust_score = 0.0
        self.seller.save(update_fields=['trust_score'])
        post.update_visibility_score()
        post.refresh_from_db()
        # engagement E = 1 (aucune vue/like), donc visibility_score == T borné.
        self.assertAlmostEqual(post.visibility_score, settings_row.trust_factor_min, places=2)


class UniqueViewTests(MarketplaceTestBase):
    def test_same_anonymous_visitor_counted_once_per_day(self):
        post = self.make_post()
        url = reverse('post-detail', args=[post.id])

        self.client.get(url)
        self.client.get(url)  # même client => même cookie anon_id

        post.refresh_from_db()
        self.assertEqual(post.views_count, 1)
        self.assertEqual(PostUniqueView.objects.filter(post=post).count(), 1)

    def test_two_different_users_both_count(self):
        post = self.make_post()
        url = reverse('post-detail', args=[post.id])

        self.client.force_authenticate(self.buyer)
        self.client.get(url)

        other = User.objects.create_user(email='other@example.com', password='x', full_name='Autre')
        self.client.force_authenticate(other)
        self.client.get(url)

        post.refresh_from_db()
        self.assertEqual(post.views_count, 2)


class TrendingBadgeTests(MarketplaceTestBase):
    def test_not_trending_without_history(self):
        post = self.make_post()
        self.assertFalse(post.is_trending())

    def test_trending_when_views_spike(self):
        from datetime import timedelta
        from django.utils import timezone

        post = self.make_post()
        today = timezone.now().date()
        # date est auto_now_add : on force la vraie date après coup avec un
        # deuxième .save(), qui n'est plus soumis à auto_now_add (seul l'INSERT l'est).
        for i in range(1, 6):
            stat = PostViewStat.objects.create(post=post, seller=self.seller, views=1)
            stat.date = today - timedelta(days=i)
            stat.save(update_fields=['date'])

        stat = PostViewStat.objects.create(post=post, seller=self.seller, views=10)
        stat.date = today
        stat.save(update_fields=['date'])

        self.assertTrue(post.is_trending())


class ShareActionTests(MarketplaceTestBase):
    def test_share_increments_counter_and_requires_auth(self):
        post = self.make_post()
        response = self.client.post(reverse('post-share', args=[post.id]))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        self.client.force_authenticate(self.buyer)
        response = self.client.post(reverse('post-share', args=[post.id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['shares_count'], 1)
