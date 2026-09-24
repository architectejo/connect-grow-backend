from rest_framework import serializers
from .models import User, BusinessProfile

class BusinessProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusinessProfile
        fields = ['business_name', 'categories', 'bio', 'logo', 'nif', 'is_verified']

class UserSerializer(serializers.ModelSerializer):
    # Inclusion du profil entreprise (imbriqué)
    business_profile = BusinessProfileSerializer(required=False)
    ville_name = serializers.CharField(source='ville.name', read_only=True)
    commune_name = serializers.CharField(source='commune.name', read_only=True)

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
            'password', 
            'business_profile',
            'date_joined'
        ]
        extra_kwargs = {
            'password': {'write_only': True}  # Sécurité : ne jamais renvoyer le mot de passe
        }

    def create(self, validated_data):
        """
        Crée un utilisateur et son profil entreprise si le type est 'ENTREPRISE'.
        """
        business_data = validated_data.pop('business_profile', None)
        
        # Utilise create_user du UserManager pour hacher le mot de passe
        user = User.objects.create_user(**validated_data)
        
        if user.user_type == 'ENTREPRISE' and business_data:
            BusinessProfile.objects.create(user=user, **business_data)
        
        return user


    # Dans UserSerializer.update
    def update(self, instance, validated_data):
        business_data = validated_data.pop('business_profile', None)
        
        # Mise à jour User
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
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