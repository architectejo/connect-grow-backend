from datetime import timedelta

from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.marketplace.models import Category, City, Commune, Post
from apps.marketplace.tests import make_test_image
from apps.reputation.models import Deal

from .models import Review


class ReviewTestBase(APITestCase):
    def setUp(self):
        city = City.objects.create(name='Kinshasa')
        self.commune = Commune.objects.create(city=city, name='Gombe')
        self.category = Category.objects.create(name='Électronique', slug='electronique')
        self.seller = User.objects.create_user(email='seller@example.com', password='x', full_name='Vendeur')
        self.buyer = User.objects.create_user(email='buyer@example.com', password='x', full_name='Acheteur')
        self.post = Post.objects.create(
            seller=self.seller, category=self.category, commune=self.commune,
            title='Un joli canapé à vendre', description='Description suffisamment longue pour le CDC.',
            price=100, main_image=make_test_image(),
        )

    def make_confirmed_deal(self, post=None, initiator=None, counterparty=None):
        deal = Deal.objects.create(
            post=post or self.post, initiator=initiator or self.buyer, counterparty=counterparty or self.seller,
        )
        deal.confirm()
        return deal


class ReviewCreationGateTests(ReviewTestBase):
    def test_review_requires_a_deal(self):
        self.client.force_authenticate(self.buyer)
        response = self.client.post('/api/interactions/reviews/', {
            'post': self.post.id, 'content': 'Très bon vendeur, je recommande.', 'rating': 5,
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_review_requires_a_confirmed_deal(self):
        deal = Deal.objects.create(post=self.post, initiator=self.buyer, counterparty=self.seller)
        self.client.force_authenticate(self.buyer)
        response = self.client.post('/api/interactions/reviews/', {
            'deal': deal.id, 'content': 'Très bon vendeur, je recommande.', 'rating': 5,
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_confirmed_deal_allows_review(self):
        deal = self.make_confirmed_deal()
        self.client.force_authenticate(self.buyer)
        response = self.client.post('/api/interactions/reviews/', {
            'deal': deal.id, 'content': 'Très bon vendeur, je recommande.', 'rating': 5,
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data['reviewed_user_id'], self.seller.id)

    def test_stranger_to_the_deal_cannot_review(self):
        deal = self.make_confirmed_deal()
        stranger = User.objects.create_user(email='stranger@example.com', password='x', full_name='Étranger')
        self.client.force_authenticate(stranger)
        response = self.client.post('/api/interactions/reviews/', {
            'deal': deal.id, 'content': 'Très bon vendeur, je recommande.', 'rating': 5,
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_only_one_review_per_party_per_deal(self):
        deal = self.make_confirmed_deal()
        self.client.force_authenticate(self.buyer)
        self.client.post('/api/interactions/reviews/', {
            'deal': deal.id, 'content': 'Très bon vendeur, je recommande.', 'rating': 5,
        })
        response = self.client.post('/api/interactions/reviews/', {
            'deal': deal.id, 'content': 'Deuxième avis sur la même affaire.', 'rating': 4,
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_both_parties_can_review_the_same_deal(self):
        deal = self.make_confirmed_deal()
        self.client.force_authenticate(self.buyer)
        r1 = self.client.post('/api/interactions/reviews/', {
            'deal': deal.id, 'content': 'Très bon vendeur, je recommande.', 'rating': 5,
        })
        self.client.force_authenticate(self.seller)
        r2 = self.client.post('/api/interactions/reviews/', {
            'deal': deal.id, 'content': 'Acheteur sérieux et ponctuel.', 'rating': 5,
        })
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r2.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r2.data['reviewed_user_id'], self.buyer.id)

    def test_content_too_short_is_rejected(self):
        deal = self.make_confirmed_deal()
        self.client.force_authenticate(self.buyer)
        response = self.client.post('/api/interactions/reviews/', {
            'deal': deal.id, 'content': 'Court', 'rating': 5,
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_rating_out_of_bounds_is_rejected(self):
        deal = self.make_confirmed_deal()
        self.client.force_authenticate(self.buyer)
        response = self.client.post('/api/interactions/reviews/', {
            'deal': deal.id, 'content': 'Contenu suffisamment long pour être valide.', 'rating': 7,
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class ReviewDailyLimitTests(ReviewTestBase):
    def test_sixth_review_in_one_day_is_rejected(self):
        self.client.force_authenticate(self.buyer)
        for i in range(5):
            post = Post.objects.create(
                seller=User.objects.create_user(email=f'seller{i}@example.com', password='x', full_name=f'V{i}'),
                category=self.category, commune=self.commune,
                title=f'Annonce numéro {i} à vendre', description='Description suffisamment longue pour le CDC.',
                price=10, main_image=make_test_image(),
            )
            deal = self.make_confirmed_deal(post=post, counterparty=post.seller)
            response = self.client.post('/api/interactions/reviews/', {
                'deal': deal.id, 'content': f'Avis numéro {i} suffisamment long.', 'rating': 5,
            })
            self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        sixth_post = Post.objects.create(
            seller=User.objects.create_user(email='seller5@example.com', password='x', full_name='V5'),
            category=self.category, commune=self.commune,
            title='Sixième annonce du jour à vendre', description='Description suffisamment longue pour le CDC.',
            price=10, main_image=make_test_image(),
        )
        sixth_deal = self.make_confirmed_deal(post=sixth_post, counterparty=sixth_post.seller)
        response = self.client.post('/api/interactions/reviews/', {
            'deal': sixth_deal.id, 'content': 'Sixième avis, devrait être refusé.', 'rating': 5,
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class ReviewEditWindowTests(ReviewTestBase):
    def test_can_edit_within_48_hours(self):
        deal = self.make_confirmed_deal()
        review = Review.objects.create(
            deal=deal, post=self.post, user=self.buyer, reviewed_user=self.seller,
            content='Avis initial suffisamment long.', rating=4,
        )
        self.client.force_authenticate(self.buyer)
        response = self.client.patch(f'/api/interactions/reviews/{review.id}/', {'content': 'Avis modifié à temps.'})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_cannot_edit_after_48_hours(self):
        deal = self.make_confirmed_deal()
        review = Review.objects.create(
            deal=deal, post=self.post, user=self.buyer, reviewed_user=self.seller,
            content='Avis initial suffisamment long.', rating=4,
        )
        Review.objects.filter(pk=review.pk).update(created_at=timezone.now() - timedelta(hours=49))
        self.client.force_authenticate(self.buyer)
        response = self.client.patch(f'/api/interactions/reviews/{review.id}/', {'content': 'Trop tard pour modifier.'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class ReviewReplyTests(ReviewTestBase):
    def test_reviewed_user_can_reply(self):
        deal = self.make_confirmed_deal()
        review = Review.objects.create(
            deal=deal, post=self.post, user=self.buyer, reviewed_user=self.seller,
            content='Avis initial suffisamment long.', rating=4,
        )
        self.client.force_authenticate(self.seller)
        response = self.client.post(f'/api/interactions/reviews/{review.id}/reply/', {
            'reply_content': 'Merci pour votre confiance !',
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_stranger_cannot_reply(self):
        deal = self.make_confirmed_deal()
        review = Review.objects.create(
            deal=deal, post=self.post, user=self.buyer, reviewed_user=self.seller,
            content='Avis initial suffisamment long.', rating=4,
        )
        self.client.force_authenticate(self.buyer)
        response = self.client.post(f'/api/interactions/reviews/{review.id}/reply/', {
            'reply_content': 'Je réponds à mon propre avis.',
        })
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class ContactAggregateCommandTests(ReviewTestBase):
    def test_refresh_dashboard_aggregates_counts_todays_contacts(self):
        from django.core.management import call_command

        from .models import ContactRequest, ContactStat

        ContactRequest.objects.create(post=self.post, sender=self.buyer, message='Bonjour')
        ContactRequest.objects.create(post=self.post, sender=self.buyer, message='Toujours disponible ?')

        call_command('refresh_dashboard_aggregates', verbosity=0)

        stat = ContactStat.objects.get(post=self.post)
        self.assertEqual(stat.count, 2)
        self.assertEqual(stat.seller_id, self.seller.id)
