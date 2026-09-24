from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import FileResponse
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView
from rest_framework.response import Response

from .models import BusinessProfile, KycDocument, OtpCode, User, phone_validator
from .serializers import KycDocumentSerializer, UserSerializer
from .sms import send_otp_sms

class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    permission_classes = [permissions.AllowAny] # Tout le monde peut s'inscrire
    serializer_class = UserSerializer

class UserDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated] # Nécessite d'être connecté

    def get_object(self):
        return self.request.user

class ChangePasswordView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user
        old_password = request.data.get("old_password")
        new_password = request.data.get("new_password")

        # Vérification de l'ancien mot de passe
        if not user.check_password(old_password):
            return Response(
                {"error": "L'ancien mot de passe est incorrect."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Mise à jour du mot de passe
        user.set_password(new_password)
        user.save()
        return Response({"message": "Mot de passe mis à jour avec succès."}, status=status.HTTP_200_OK)

class BusinessListView(generics.ListAPIView):
    """
    Vue publique pour lister toutes les entreprises inscrites sur la plateforme.
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = UserSerializer # On peut utiliser UserSerializer ou un plus léger

    def get_queryset(self):
        from django.db.models import Q
        # On ne récupère que les utilisateurs de type ENTREPRISE
        queryset = User.objects.filter(user_type='ENTREPRISE').select_related('business_profile', 'commune', 'ville')

        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(business_profile__business_name__icontains=search) |
                Q(full_name__icontains=search) |
                Q(business_profile__bio__icontains=search)
            )

        return queryset


class OtpRequestThrottle(AnonRateThrottle):
    scope = 'otp'


class OtpRequestView(APIView):
    """CDC 3.1 : envoi d'un code OTP par SMS pour l'inscription, la connexion
    ou la réinitialisation du mot de passe."""

    permission_classes = [permissions.AllowAny]
    throttle_classes = [OtpRequestThrottle]

    def post(self, request):
        phone = request.data.get('phone', '')
        purpose = request.data.get('purpose', OtpCode.PURPOSE_REGISTER)

        if purpose not in dict(OtpCode.PURPOSE_CHOICES):
            return Response({'error': "purpose invalide."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            phone_validator(phone)
        except DjangoValidationError:
            return Response(
                {'error': "Numéro invalide. Format attendu : +243XXXXXXXXX."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user_exists = User.objects.filter(phone=phone).exists()
        if purpose == OtpCode.PURPOSE_REGISTER and user_exists:
            return Response({'error': "Un compte existe déjà avec ce numéro."}, status=status.HTTP_400_BAD_REQUEST)
        if purpose in (OtpCode.PURPOSE_LOGIN, OtpCode.PURPOSE_PASSWORD_RESET) and not user_exists:
            return Response({'error': "Aucun compte associé à ce numéro."}, status=status.HTTP_400_BAD_REQUEST)

        _, code = OtpCode.issue(phone, purpose)
        send_otp_sms(phone, code, purpose)

        return Response(
            {'message': "Code envoyé par SMS.", 'expires_in_minutes': OtpCode.VALIDITY_MINUTES},
            status=status.HTTP_200_OK,
        )


class PasswordResetConfirmView(APIView):
    """CDC 3.1 : réinitialisation du mot de passe par OTP."""

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        phone = request.data.get('phone')
        code = request.data.get('code')
        new_password = request.data.get('new_password')

        if not (phone and code and new_password):
            return Response(
                {'error': "phone, code et new_password sont requis."}, status=status.HTTP_400_BAD_REQUEST
            )

        otp = (
            OtpCode.objects.filter(phone=phone, purpose=OtpCode.PURPOSE_PASSWORD_RESET, is_used=False)
            .order_by('-created_at')
            .first()
        )
        if not otp or not otp.verify(code):
            return Response({'error': "Code invalide ou expiré."}, status=status.HTTP_400_BAD_REQUEST)

        user = User.objects.filter(phone=phone).first()
        if not user:
            return Response({'error': "Aucun compte associé à ce numéro."}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(new_password)
        user.save(update_fields=['password'])
        return Response({'message': "Mot de passe mis à jour avec succès."}, status=status.HTTP_200_OK)


class KycDocumentListCreateView(generics.ListCreateAPIView):
    """Soumission et suivi des pièces KYC d'un Profil Business (CDC 3.1)."""

    serializer_class = KycDocumentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return KycDocument.objects.filter(business_profile__user=self.request.user)

    def perform_create(self, serializer):
        try:
            business_profile = self.request.user.business_profile
        except BusinessProfile.DoesNotExist:
            from rest_framework.exceptions import ValidationError
            raise ValidationError("Un profil Business est requis avant de soumettre des pièces KYC.")
        serializer.save(business_profile=business_profile)


class KycReviewQueueView(generics.ListAPIView):
    """File de vérification Business pour la modération (CDC 3.11)."""

    serializer_class = KycDocumentSerializer
    permission_classes = [permissions.IsAdminUser]
    queryset = KycDocument.objects.filter(status=KycDocument.STATUS_EN_ATTENTE).select_related('business_profile')


class KycDecisionView(APIView):
    """Validation ou refus motivé d'une pièce KYC par la modération (CDC 3.11)."""

    permission_classes = [permissions.IsAdminUser]

    def post(self, request, pk):
        try:
            doc = KycDocument.objects.select_related('business_profile').get(pk=pk)
        except KycDocument.DoesNotExist:
            return Response({'error': "Document introuvable."}, status=status.HTTP_404_NOT_FOUND)

        decision = request.data.get('decision')
        if decision not in (KycDocument.STATUS_VALIDE, KycDocument.STATUS_REFUSE):
            return Response({'error': "decision doit être VALIDE ou REFUSE."}, status=status.HTTP_400_BAD_REQUEST)

        doc.status = decision
        doc.rejection_reason = request.data.get('reason', '') if decision == KycDocument.STATUS_REFUSE else ''
        doc.reviewed_by = request.user
        doc.reviewed_at = timezone.now()
        doc.save(update_fields=['status', 'rejection_reason', 'reviewed_by', 'reviewed_at'])

        if decision == KycDocument.STATUS_VALIDE:
            required_types = {
                KycDocument.DOC_RCCM, KycDocument.DOC_ID_NATIONALE, KycDocument.DOC_PIECE_GERANT,
            }
            validated_types = set(
                doc.business_profile.kyc_documents
                .filter(status=KycDocument.STATUS_VALIDE)
                .values_list('document_type', flat=True)
            )
            if required_types.issubset(validated_types):
                doc.business_profile.is_verified = True
                doc.business_profile.save(update_fields=['is_verified'])

        return Response(KycDocumentSerializer(doc).data, status=status.HTTP_200_OK)


class KycDocumentDownloadView(APIView):
    """Accès aux pièces KYC réservé aux administrateurs (CDC 4.2, 5.8)."""

    permission_classes = [permissions.IsAdminUser]

    def get(self, request, pk):
        try:
            doc = KycDocument.objects.get(pk=pk)
        except KycDocument.DoesNotExist:
            return Response({'error': "Document introuvable."}, status=status.HTTP_404_NOT_FOUND)
        return FileResponse(doc.file.open('rb'), as_attachment=True, filename=doc.file.name)
