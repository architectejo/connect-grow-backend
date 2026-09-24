from rest_framework import serializers
from rest_framework_simplejwt.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import BusinessProfile, KycDocument, OtpCode, User


class BusinessProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusinessProfile
        fields = ['business_name', 'categories', 'bio', 'logo', 'nif', 'is_verified']
        # is_verified ne se décide que par la validation KYC de la modération
        # (KycDecisionView), jamais par l'utilisateur via son propre profil (CDC 3.1).
        read_only_fields = ['is_verified']


class UserSerializer(serializers.ModelSerializer):
    # Inclusion du profil entreprise (imbriqué)
    business_profile = BusinessProfileSerializer(required=False)
    ville_name = serializers.CharField(source='ville.name', read_only=True)
    commune_name = serializers.CharField(source='commune.name', read_only=True)
    # Fourni uniquement lors d'une inscription/modification par téléphone (CDC 3.1) ;
    # ce n'est pas un champ du modèle, il est retiré dans validate().
    otp_code = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = User
        fields = [
            'id',
            'email',
            'photo',
            'full_name',
            'user_type',
            'ville',
            'ville_name',
            'commune',
            'commune_name',
            'phone',
            'phone_verified',
            'password',
            'otp_code',
            'business_profile',
            'date_joined'
        ]
        extra_kwargs = {
            'password': {'write_only': True},  # Sécurité : ne jamais renvoyer le mot de passe
            'phone_verified': {'read_only': True},
        }

    def validate(self, attrs):
        """Si un téléphone est fourni (à la création ou pour le changer), il doit
        être accompagné d'un code OTP valide (purpose=REGISTER) — CDC 3.1."""
        phone = attrs.get('phone')
        otp_code = attrs.pop('otp_code', None)

        self._phone_just_verified = False
        if phone:
            if not otp_code:
                raise serializers.ValidationError(
                    {'otp_code': "Un code de vérification est requis pour ce numéro de téléphone."}
                )
            otp = (
                OtpCode.objects.filter(phone=phone, purpose=OtpCode.PURPOSE_REGISTER, is_used=False)
                .order_by('-created_at')
                .first()
            )
            if not otp or not otp.verify(otp_code):
                raise serializers.ValidationError({'otp_code': "Code invalide ou expiré."})
            self._phone_just_verified = True

        return attrs

    def create(self, validated_data):
        """
        Crée un utilisateur et son profil entreprise si le type est 'ENTREPRISE'.
        """
        business_data = validated_data.pop('business_profile', None)

        # Utilise create_user du UserManager pour hacher le mot de passe
        user = User.objects.create_user(**validated_data)

        if self._phone_just_verified:
            user.phone_verified = True
            user.save(update_fields=['phone_verified'])

        if user.user_type == 'ENTREPRISE' and business_data:
            BusinessProfile.objects.create(user=user, **business_data)

        return user


    # Dans UserSerializer.update
    def update(self, instance, validated_data):
        business_data = validated_data.pop('business_profile', None)

        # Mise à jour User
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if self._phone_just_verified:
            instance.phone_verified = True
        instance.save()

        # Mise à jour Profil
        if instance.user_type == 'ENTREPRISE' and business_data:
            business_profile, _ = BusinessProfile.objects.get_or_create(user=instance)
            for attr, value in business_data.items():
                # Si value est None ou vide et que c'est une image,
                # on vérifie si on veut vraiment l'écraser
                setattr(business_profile, attr, value)
            business_profile.save()

        return instance

    def to_representation(self, instance):
        """
        S'assure que business_profile est null dans la réponse JSON
        si l'utilisateur n'est pas de type ENTREPRISE.
        """
        data = super().to_representation(instance)
        try:
            # Vérifie si le profil existe réellement
            if not hasattr(instance, 'business_profile'):
                data['business_profile'] = None
        except BusinessProfile.DoesNotExist:
            data['business_profile'] = None
        return data


class IdentifierTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Connexion par e-mail OU par téléphone (CDC 3.1), au choix. Remplace la
    validation par défaut de SimpleJWT (qui n'accepte que USERNAME_FIELD) sans
    passer par authenticate()/ModelBackend, qui suppose un email toujours présent."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields[self.username_field].required = False
        self.fields['phone'] = serializers.CharField(required=False)

    def validate(self, attrs):
        email = attrs.get(self.username_field)
        phone = attrs.get('phone')
        password = attrs.get('password')

        if not password or (not email and not phone):
            raise serializers.ValidationError("email (ou phone) et password sont requis.")

        user = User.objects.filter(email=email).first() if email else User.objects.filter(phone=phone).first()
        if user is None or not user.is_active or not user.check_password(password):
            raise AuthenticationFailed(
                "Aucun compte actif trouvé avec les identifiants fournis.", 'no_active_account'
            )

        refresh = self.get_token(user)
        return {
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        }


class KycDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = KycDocument
        fields = ['id', 'document_type', 'file', 'status', 'rejection_reason', 'created_at', 'reviewed_at']
        read_only_fields = ['id', 'status', 'rejection_reason', 'created_at', 'reviewed_at']
