from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from .models import BusinessProfile, KycDocument, OtpCode, User


class OtpCodeModelTests(TestCase):
    """CDC 3.1 : OTP à 6 chiffres, valable 10 minutes, 3 tentatives maximum."""

    def test_issue_returns_six_digit_code(self):
        _, code = OtpCode.issue('+243811111111', OtpCode.PURPOSE_REGISTER)
        self.assertEqual(len(code), 6)
        self.assertTrue(code.isdigit())

    def test_correct_code_verifies_once(self):
        otp, code = OtpCode.issue('+243811111111', OtpCode.PURPOSE_REGISTER)
        self.assertTrue(otp.verify(code))
        # Usage unique : une deuxième vérification du même code échoue.
        self.assertFalse(otp.verify(code))

    def test_wrong_code_is_rejected_and_counts_as_attempt(self):
        otp, _ = OtpCode.issue('+243811111111', OtpCode.PURPOSE_REGISTER)
        self.assertFalse(otp.verify('000000'))
        otp.refresh_from_db()
        self.assertEqual(otp.attempts, 1)

    def test_max_three_attempts(self):
        otp, code = OtpCode.issue('+243811111111', OtpCode.PURPOSE_REGISTER)
        for _ in range(OtpCode.MAX_ATTEMPTS):
            otp.verify('000000')
        # Même le bon code est refusé au-delà de la limite de tentatives.
        self.assertFalse(otp.verify(code))

    def test_expired_code_is_rejected(self):
        otp, code = OtpCode.issue('+243811111111', OtpCode.PURPOSE_REGISTER)
        otp.expires_at = timezone.now() - timedelta(seconds=1)
        otp.save(update_fields=['expires_at'])
        self.assertFalse(otp.verify(code))

    def test_issuing_new_code_invalidates_previous_one(self):
        otp1, code1 = OtpCode.issue('+243811111111', OtpCode.PURPOSE_REGISTER)
        OtpCode.issue('+243811111111', OtpCode.PURPOSE_REGISTER)
        otp1.refresh_from_db()
        self.assertTrue(otp1.is_used)
        self.assertFalse(otp1.verify(code1))


class RegistrationApiTests(APITestCase):
    def test_register_by_email_does_not_require_otp(self):
        response = self.client.post(reverse('register'), {
            'email': 'alice@example.com',
            'password': 'un-mot-de-passe-solide',
            'full_name': 'Alice',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertTrue(User.objects.filter(email='alice@example.com').exists())

    def test_register_by_phone_without_otp_is_rejected(self):
        response = self.client.post(reverse('register'), {
            'phone': '+243822222222',
            'password': 'un-mot-de-passe-solide',
            'full_name': 'Bob',
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(User.objects.filter(phone='+243822222222').exists())

    def test_register_by_phone_with_valid_otp_succeeds(self):
        phone = '+243822222223'
        _, code = OtpCode.issue(phone, OtpCode.PURPOSE_REGISTER)
        response = self.client.post(reverse('register'), {
            'phone': phone,
            'otp_code': code,
            'password': 'un-mot-de-passe-solide',
            'full_name': 'Carole',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        user = User.objects.get(phone=phone)
        self.assertTrue(user.phone_verified)

    def test_register_by_phone_with_wrong_otp_is_rejected(self):
        phone = '+243822222224'
        OtpCode.issue(phone, OtpCode.PURPOSE_REGISTER)
        response = self.client.post(reverse('register'), {
            'phone': phone,
            'otp_code': '000000',
            'password': 'un-mot-de-passe-solide',
            'full_name': 'David',
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(User.objects.filter(phone=phone).exists())


class LoginApiTests(APITestCase):
    def setUp(self):
        self.password = 'un-mot-de-passe-solide'
        self.email_user = User.objects.create_user(email='eve@example.com', password=self.password, full_name='Eve')
        self.phone_user = User.objects.create_user(
            phone='+243833333333', password=self.password, full_name='Farid',
        )

    def test_login_with_email(self):
        response = self.client.post(reverse('token_obtain_pair'), {
            'email': 'eve@example.com', 'password': self.password,
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertIn('access', response.data)

    def test_login_with_phone(self):
        response = self.client.post(reverse('token_obtain_pair'), {
            'phone': '+243833333333', 'password': self.password,
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertIn('access', response.data)

    def test_login_with_wrong_password_is_rejected(self):
        response = self.client.post(reverse('token_obtain_pair'), {
            'email': 'eve@example.com', 'password': 'mauvais-mot-de-passe',
        })
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class PasswordResetApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            phone='+243844444444', password='ancien-mot-de-passe', full_name='Grace',
        )

    def test_reset_with_valid_otp(self):
        _, code = OtpCode.issue(self.user.phone, OtpCode.PURPOSE_PASSWORD_RESET)
        response = self.client.post(reverse('password_reset_confirm'), {
            'phone': self.user.phone, 'code': code, 'new_password': 'nouveau-mot-de-passe',
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('nouveau-mot-de-passe'))

    def test_reset_with_invalid_otp_is_rejected(self):
        OtpCode.issue(self.user.phone, OtpCode.PURPOSE_PASSWORD_RESET)
        response = self.client.post(reverse('password_reset_confirm'), {
            'phone': self.user.phone, 'code': '000000', 'new_password': 'nouveau-mot-de-passe',
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('ancien-mot-de-passe'))


class KycDocumentApiTests(APITestCase):
    def setUp(self):
        self.business_user = User.objects.create_user(
            email='biz@example.com', password='x', full_name='Boutique', user_type='ENTREPRISE',
        )
        self.business_profile = BusinessProfile.objects.create(
            user=self.business_user, business_name='Ma Boutique',
        )
        self.admin = User.objects.create_user(
            email='admin@example.com', password='x', full_name='Admin', is_staff=True,
        )

    def test_non_business_user_cannot_submit_kyc(self):
        user = User.objects.create_user(email='particulier@example.com', password='x', full_name='Particulier')
        self.client.force_authenticate(user)
        response = self.client.post(reverse('kyc_documents'), {'document_type': KycDocument.DOC_RCCM})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_admin_can_validate_kyc_document(self):
        doc = KycDocument.objects.create(
            business_profile=self.business_profile, document_type=KycDocument.DOC_RCCM,
        )
        self.client.force_authenticate(self.admin)
        response = self.client.post(
            reverse('kyc_decision', args=[doc.pk]), {'decision': KycDocument.STATUS_VALIDE},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        doc.refresh_from_db()
        self.assertEqual(doc.status, KycDocument.STATUS_VALIDE)

    def test_non_admin_cannot_access_review_queue(self):
        self.client.force_authenticate(self.business_user)
        response = self.client.get(reverse('kyc_review_queue'))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_user_cannot_self_declare_business_verified(self):
        self.client.force_authenticate(self.business_user)
        response = self.client.patch(reverse('user_me'), {
            'business_profile': {'business_name': 'Ma Boutique', 'is_verified': True},
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.business_profile.refresh_from_db()
        self.assertFalse(self.business_profile.is_verified)

    def test_business_verified_once_all_required_documents_validated(self):
        for doc_type in (KycDocument.DOC_RCCM, KycDocument.DOC_ID_NATIONALE, KycDocument.DOC_PIECE_GERANT):
            doc = KycDocument.objects.create(business_profile=self.business_profile, document_type=doc_type)
            self.client.force_authenticate(self.admin)
            self.client.post(reverse('kyc_decision', args=[doc.pk]), {'decision': KycDocument.STATUS_VALIDE})
        self.business_profile.refresh_from_db()
        self.assertTrue(self.business_profile.is_verified)
