from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.interactions.models import ContactRequest, Review
from apps.marketplace.models import Category, City, Commune, Post
from apps.marketplace.tests import make_test_image

from .models import Deal, TrustScoreSettings


class ReputationTestBase(APITestCase):
    def setUp(self):
        city = City.objects.create(name='Kinshasa')
        self.commune = Commune.objects.create(city=city, name='Gombe')
        self.category = Category.objects.create(name='Électronique', slug='electronique')
        self.seller = User.objects.create_user(email='seller@example.com', password='x', full_name='Vendeur')
        self.buyer = User.objects.create_user(email='buyer@example.com', password='x', full_name='Acheteur')
        self.other = User.objects.create_user(email='other@example.com', password='x', full_name='Tiers')
        self.post = Post.objects.create(
            seller=self.seller, category=self.category, commune=self.commune,
            title='Un joli canapé à vendre', description='Description suffisamment longue pour le CDC.',
            price=100, main_image=make_test_image(),
        )
        ContactRequest.objects.create(post=self.post, sender=self.buyer, message='Bonjour, toujours dispo ?')


class DealCreationTests(ReputationTestBase):
    def test_buyer_can_declare_deal_with_seller(self):
        self.client.force_authenticate(self.buyer)
        response = self.client.post('/api/reputation/deals/', {
            'post': self.post.id, 'counterparty': self.seller.id,
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data['status'], Deal.STATUS_PENDING)

    def test_seller_can_declare_deal_with_a_contact(self):
        self.client.force_authenticate(self.seller)
        response = self.client.post('/api/reputation/deals/', {
            'post': self.post.id, 'counterparty': self.buyer.id,
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

    def test_cannot_declare_deal_with_self(self):
        self.client.force_authenticate(self.buyer)
        response = self.client.post('/api/reputation/deals/', {
            'post': self.post.id, 'counterparty': self.buyer.id,
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_buyer_cannot_declare_deal_with_uninvolved_user(self):
        self.client.force_authenticate(self.buyer)
        response = self.client.post('/api/reputation/deals/', {
            'post': self.post.id, 'counterparty': self.other.id,
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_seller_cannot_declare_deal_with_non_contact(self):
        self.client.force_authenticate(self.seller)
        response = self.client.post('/api/reputation/deals/', {
            'post': self.post.id, 'counterparty': self.other.id,
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class DealConfirmationTests(ReputationTestBase):
    def setUp(self):
        super().setUp()
        self.deal = Deal.objects.create(post=self.post, initiator=self.buyer, counterparty=self.seller)

    def test_only_counterparty_can_confirm(self):
        self.client.force_authenticate(self.buyer)
        response = self.client.post(f'/api/reputation/deals/{self.deal.id}/confirm/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_counterparty_confirms(self):
        self.client.force_authenticate(self.seller)
        response = self.client.post(f'/api/reputation/deals/{self.deal.id}/confirm/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.deal.refresh_from_db()
        self.assertEqual(self.deal.status, Deal.STATUS_CONFIRMED)
        self.assertIsNotNone(self.deal.confirmed_at)

    def test_cannot_confirm_twice(self):
        self.deal.confirm()
        self.client.force_authenticate(self.seller)
        response = self.client.post(f'/api/reputation/deals/{self.deal.id}/confirm/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class TrustScoreSignalTests(ReputationTestBase):
    def make_confirmed_deal(self, initiator, counterparty):
        deal = Deal.objects.create(post=self.post, initiator=initiator, counterparty=counterparty)
        deal.confirm()
        return deal

    def test_review_creation_updates_trust_score(self):
        deal = self.make_confirmed_deal(self.buyer, self.seller)
        Review.objects.create(
            deal=deal, post=self.post, user=self.buyer, reviewed_user=self.seller,
            content='Vendeur très sérieux et rapide.', rating=5,
        )
        self.seller.refresh_from_db()
        settings_row = TrustScoreSettings.get_solo()
        expected = (settings_row.neutral_weight * settings_row.neutral_rating + 5) / (settings_row.neutral_weight + 1)
        self.assertAlmostEqual(self.seller.trust_score, round(expected, 2))
        self.assertEqual(self.seller.reviews_count, 1)

    def test_deleting_review_recomputes_trust_score(self):
        deal = self.make_confirmed_deal(self.buyer, self.seller)
        review = Review.objects.create(
            deal=deal, post=self.post, user=self.buyer, reviewed_user=self.seller,
            content='Vendeur très sérieux et rapide.', rating=1,
        )
        self.seller.refresh_from_db()
        self.assertEqual(self.seller.reviews_count, 1)

        review.delete()
        self.seller.refresh_from_db()
        self.assertEqual(self.seller.reviews_count, 0)
        self.assertEqual(self.seller.trust_score, 3.5)  # retombe à la note neutre

    def test_hidden_review_excluded_from_trust_score(self):
        deal = self.make_confirmed_deal(self.buyer, self.seller)
        review = Review.objects.create(
            deal=deal, post=self.post, user=self.buyer, reviewed_user=self.seller,
            content='Vendeur très sérieux et rapide.', rating=1,
        )
        self.seller.refresh_from_db()
        self.assertLess(self.seller.trust_score, 3.5)

        review.is_hidden = True
        review.save()
        self.seller.refresh_from_db()
        self.assertEqual(self.seller.trust_score, 3.5)
        self.assertEqual(self.seller.reviews_count, 0)

    def test_new_review_refreshes_seller_posts_visibility_score(self):
        deal = self.make_confirmed_deal(self.buyer, self.seller)
        before = self.post.visibility_score
        Review.objects.create(
            deal=deal, post=self.post, user=self.buyer, reviewed_user=self.seller,
            content='Vendeur très sérieux et rapide.', rating=5,
        )
        self.post.refresh_from_db()
        self.assertNotEqual(before, self.post.visibility_score)


class CrossedReviewsDetectionTests(ReputationTestBase):
    def make_post(self, seller):
        return Post.objects.create(
            seller=seller, category=self.category, commune=self.commune,
            title='Une annonce quelconque à vendre', description='Description suffisamment longue pour le CDC.',
            price=50, main_image=make_test_image(),
        )

    def make_confirmed_deal(self, initiator, counterparty, post):
        deal = Deal.objects.create(post=post, initiator=initiator, counterparty=counterparty)
        deal.confirm()
        return deal

    def test_three_mutual_deals_trigger_a_report(self):
        from django.contrib.contenttypes.models import ContentType

        from apps.moderation.models import Report

        for _ in range(3):
            post = self.make_post(self.seller)
            deal = self.make_confirmed_deal(self.buyer, self.seller, post=post)
            Review.objects.create(
                deal=deal, post=post, user=self.buyer, reviewed_user=self.seller,
                content='Vendeur très sérieux et rapide.', rating=5,
            )
            last_review = Review.objects.create(
                deal=deal, post=post, user=self.seller, reviewed_user=self.buyer,
                content='Acheteur sérieux et ponctuel.', rating=5,
            )

        self.assertTrue(
            Report.objects.filter(
                content_type=ContentType.objects.get_for_model(Review),
                object_id=last_review.id,
                reason=Report.REASON_AVIS_CROISES,
            ).exists()
        )

    def test_two_mutual_deals_do_not_trigger_a_report(self):
        from django.contrib.contenttypes.models import ContentType

        from apps.moderation.models import Report

        for _ in range(2):
            post = self.make_post(self.seller)
            deal = self.make_confirmed_deal(self.buyer, self.seller, post=post)
            Review.objects.create(
                deal=deal, post=post, user=self.buyer, reviewed_user=self.seller,
                content='Vendeur très sérieux et rapide.', rating=5,
            )
            Review.objects.create(
                deal=deal, post=post, user=self.seller, reviewed_user=self.buyer,
                content='Acheteur sérieux et ponctuel.', rating=5,
            )

        self.assertFalse(
            Report.objects.filter(
                content_type=ContentType.objects.get_for_model(Review), reason=Report.REASON_AVIS_CROISES,
            ).exists()
        )
