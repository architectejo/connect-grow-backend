from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.marketplace.models import Category, City, Commune, Post
from apps.marketplace.tests import make_test_image

from .models import AuditLog, ForbiddenItem, Report, Sanction


class ModerationTestBase(APITestCase):
    def setUp(self):
        call_command('setup_roles', verbosity=0)
        city = City.objects.create(name='Kinshasa')
        self.commune = Commune.objects.create(city=city, name='Gombe')
        self.category = Category.objects.create(name='Électronique', slug='electronique')

        self.seller = User.objects.create_user(email='seller@example.com', password='x', full_name='Vendeur')
        self.reporter = User.objects.create_user(email='reporter@example.com', password='x', full_name='Rapporteur')
        self.moderator = User.objects.create_user(
            email='mod@example.com', password='x', full_name='Modo', is_staff=True,
        )
        self.moderator.groups.add(Group.objects.get(name='Modérateur'))
        self.admin = User.objects.create_user(
            email='admin@example.com', password='x', full_name='Admin', is_staff=True,
        )
        self.admin.groups.add(Group.objects.get(name='Administrateur'))

        self.post = Post.objects.create(
            seller=self.seller, category=self.category, commune=self.commune,
            title='Un joli canapé à vendre', description='Description suffisamment longue pour le CDC.',
            price=100, main_image=make_test_image(),
        )


class ReportFlowTests(ModerationTestBase):
    def test_any_authenticated_user_can_report_a_post(self):
        self.client.force_authenticate(self.reporter)
        response = self.client.post('/api/moderation/reports/', {
            'target_type': 'POST', 'object_id': self.post.id, 'reason': 'ARNAQUE', 'description': 'Prix suspect.',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data['status'], Report.STATUS_EN_ATTENTE)

    def test_report_rejects_unknown_target(self):
        self.client.force_authenticate(self.reporter)
        response = self.client.post('/api/moderation/reports/', {
            'target_type': 'POST', 'object_id': 999999, 'reason': 'ARNAQUE',
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_anonymous_user_cannot_report(self):
        response = self.client.post('/api/moderation/reports/', {
            'target_type': 'POST', 'object_id': self.post.id, 'reason': 'ARNAQUE',
        })
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_staff_cannot_list_reports(self):
        self.client.force_authenticate(self.reporter)
        response = self.client.get('/api/moderation/reports/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_moderator_can_claim_and_resolve(self):
        report = Report.objects.create(
            content_type=ContentType.objects.get_for_model(Post), object_id=self.post.id,
            reporter=self.reporter, reason=Report.REASON_ARNAQUE,
        )
        self.client.force_authenticate(self.moderator)

        claim_response = self.client.post(f'/api/moderation/reports/{report.id}/claim/')
        self.assertEqual(claim_response.status_code, status.HTTP_200_OK)
        report.refresh_from_db()
        self.assertEqual(report.status, Report.STATUS_EN_COURS)
        self.assertEqual(report.assigned_to, self.moderator)

        resolve_response = self.client.post(f'/api/moderation/reports/{report.id}/resolve/', {
            'notes': "Annonce vérifiée, pas d'anomalie.",
        })
        self.assertEqual(resolve_response.status_code, status.HTTP_200_OK)
        report.refresh_from_db()
        self.assertEqual(report.status, Report.STATUS_TRAITE)
        self.assertIsNotNone(report.resolved_at)

    def test_resolving_a_report_writes_an_audit_log(self):
        report = Report.objects.create(
            content_type=ContentType.objects.get_for_model(Post), object_id=self.post.id,
            reporter=self.reporter, reason=Report.REASON_ARNAQUE,
        )
        self.client.force_authenticate(self.moderator)
        self.client.post(f'/api/moderation/reports/{report.id}/resolve/', {'notes': 'ok'})
        self.assertTrue(AuditLog.objects.filter(action='REPORT_RESOLVED', actor=self.moderator).exists())


class SanctionRoleTests(ModerationTestBase):
    def test_moderator_can_issue_warning(self):
        self.client.force_authenticate(self.moderator)
        response = self.client.post('/api/moderation/sanctions/', {
            'user': self.seller.id, 'sanction_type': Sanction.TYPE_AVERTISSEMENT, 'reason': 'Description imprécise.',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

    def test_moderator_cannot_ban(self):
        self.client.force_authenticate(self.moderator)
        response = self.client.post('/api/moderation/sanctions/', {
            'user': self.seller.id, 'sanction_type': Sanction.TYPE_BANNISSEMENT, 'reason': 'Fraude avérée.',
        })
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_administrator_can_ban(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post('/api/moderation/sanctions/', {
            'user': self.seller.id, 'sanction_type': Sanction.TYPE_BANNISSEMENT, 'reason': 'Fraude avérée.',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.seller.refresh_from_db()
        self.assertFalse(self.seller.is_active)

    def test_hiding_a_post_requires_related_post(self):
        self.client.force_authenticate(self.moderator)
        response = self.client.post('/api/moderation/sanctions/', {
            'user': self.seller.id, 'sanction_type': Sanction.TYPE_MASQUAGE_ANNONCE, 'reason': 'Produit interdit.',
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_hiding_a_post_deactivates_it(self):
        self.client.force_authenticate(self.moderator)
        response = self.client.post('/api/moderation/sanctions/', {
            'user': self.seller.id, 'sanction_type': Sanction.TYPE_MASQUAGE_ANNONCE,
            'related_post': self.post.id, 'reason': 'Produit interdit.',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.post.refresh_from_db()
        self.assertFalse(self.post.is_active)

    def test_lifting_a_ban_reactivates_the_user(self):
        self.client.force_authenticate(self.admin)
        sanction = Sanction.objects.create(
            user=self.seller, sanction_type=Sanction.TYPE_BANNISSEMENT, reason='x', issued_by=self.admin,
        )
        sanction.apply()
        self.seller.refresh_from_db()
        self.assertFalse(self.seller.is_active)

        response = self.client.post(f'/api/moderation/sanctions/{sanction.id}/lift/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.seller.refresh_from_db()
        self.assertTrue(self.seller.is_active)


class ForbiddenItemPermissionTests(ModerationTestBase):
    def test_anyone_can_list(self):
        ForbiddenItem.objects.create(keyword='arme à feu')
        response = self.client.get('/api/moderation/forbidden-items/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_only_admin_can_create(self):
        self.client.force_authenticate(self.reporter)
        response = self.client.post('/api/moderation/forbidden-items/', {'keyword': 'contrefaçon'})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(self.admin)
        response = self.client.post('/api/moderation/forbidden-items/', {'keyword': 'contrefaçon'})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)


class DashboardTests(ModerationTestBase):
    def test_dashboard_requires_staff(self):
        self.client.force_authenticate(self.reporter)
        response = self.client.get('/api/moderation/dashboard/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_dashboard_returns_counts(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get('/api/moderation/dashboard/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('pending_reports_count', response.data)


class LiftExpiredSanctionsCommandTests(ModerationTestBase):
    def test_only_expired_temporary_suspensions_are_lifted(self):
        from datetime import timedelta

        from django.core.management import call_command
        from django.utils import timezone

        expired = Sanction.objects.create(
            user=self.seller, sanction_type=Sanction.TYPE_SUSPENSION_TEMPORAIRE, reason='x',
            issued_by=self.admin, ends_at=timezone.now() - timedelta(days=1),
        )
        expired.apply()
        still_running = Sanction.objects.create(
            user=self.seller, sanction_type=Sanction.TYPE_SUSPENSION_TEMPORAIRE, reason='y',
            issued_by=self.admin, ends_at=timezone.now() + timedelta(days=5),
        )

        call_command('lift_expired_sanctions', verbosity=0)

        expired.refresh_from_db()
        still_running.refresh_from_db()
        self.assertFalse(expired.is_active)
        self.assertTrue(still_running.is_active)
        self.seller.refresh_from_db()
        self.assertTrue(self.seller.is_active)  # levée -> compte réactivé
        self.assertTrue(AuditLog.objects.filter(action='SANCTION_AUTO_LIFTED').exists())
