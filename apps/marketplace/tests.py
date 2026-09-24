import io

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from PIL import Image
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User
from .models import Category, City, Commune, Favorite, Post, PostImage


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
