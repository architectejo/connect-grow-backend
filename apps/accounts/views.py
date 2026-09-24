from rest_framework import generics, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from .serializers import UserSerializer
from .models import User

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