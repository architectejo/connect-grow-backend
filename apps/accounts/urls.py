from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from .serializers import IdentifierTokenObtainPairSerializer
from .views import (
    BusinessListView,
    ChangePasswordView,
    KycDecisionView,
    KycDocumentDownloadView,
    KycDocumentListCreateView,
    KycReviewQueueView,
    OtpRequestView,
    PasswordResetConfirmView,
    RegisterView,
    UserDetailView,
)


class LoginView(TokenObtainPairView):
    # Connexion par e-mail ou par téléphone (CDC 3.1).
    serializer_class = IdentifierTokenObtainPairSerializer


urlpatterns = [
    # Inscription
    path('register/', RegisterView.as_view(), name='register'),

    # Connexion (Obtenir le Token)
    path('login/', LoginView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # OTP et mot de passe
    path('otp/request/', OtpRequestView.as_view(), name='otp_request'),
    path('password-reset/confirm/', PasswordResetConfirmView.as_view(), name='password_reset_confirm'),

    # Profil actuel
    path('me/', UserDetailView.as_view(), name='user_me'),

    path('change-password/', ChangePasswordView.as_view(), name='change_password'),
    path('businesses/', BusinessListView.as_view(), name='business_list'),

    # KYC Business (CDC 3.1, 3.11)
    path('kyc/documents/', KycDocumentListCreateView.as_view(), name='kyc_documents'),
    path('kyc/review-queue/', KycReviewQueueView.as_view(), name='kyc_review_queue'),
    path('kyc/documents/<int:pk>/decision/', KycDecisionView.as_view(), name='kyc_decision'),
    path('kyc/documents/<int:pk>/download/', KycDocumentDownloadView.as_view(), name='kyc_download'),
]
