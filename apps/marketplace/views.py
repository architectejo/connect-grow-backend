from rest_framework.views import APIView
from django.db.models import Sum
from datetime import timedelta
from django.utils.timezone import now
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import viewsets, permissions
from .models import City, Category, Post, Commune, PostViewStat
from .serializers import CitySerializer, CategorySerializer, PostSerializer, CommuneSerializer
from django.utils.timezone import now
from django.db.models import F

class CityViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = City.objects.all().prefetch_related('communes')
    serializer_class = CitySerializer
    permission_classes = [permissions.AllowAny] # Tout le monde peut voir les villes

class CommuneViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Commune.objects.all()
    serializer_class = CommuneSerializer
    permission_classes = [permissions.AllowAny] # Tout le monde peut voir les communes

class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [permissions.AllowAny] # Tout le monde peut voir les catégories

class PostViewSet(viewsets.ModelViewSet):
    serializer_class = PostSerializer

    def get_queryset(self):
        from django.db.models import Q
        # On trie par le score de visibilité "Trust & Engage" par défaut
        ordering = self.request.query_params.get('ordering', '-visibility_score')
        
        # Par défaut (Marketplace), on ne montre que ce qui n'est pas supprimé et actif
        queryset = Post.objects.filter(is_active=True, is_delete=False)
        
        # Filtre pour récupérer les annonces de l'utilisateur connecté
        my_posts = self.request.query_params.get('my_posts')
        if my_posts == 'true' and self.request.user.is_authenticated:
            return Post.objects.filter(seller=self.request.user, is_delete=False).order_by('-created_at')

        # --- FILTRES DYNAMIQUES ---
        search = self.request.query_params.get('search')
        category = self.request.query_params.get('category')
        location = self.request.query_params.get('location')

        if search:
            queryset = queryset.filter(Q(title__icontains=search) | Q(description__icontains=search))
        
        if category:
            queryset = queryset.filter(category_id=category)
            
        if location:
            queryset = queryset.filter(
                Q(commune__name__icontains=location) | 
                Q(commune__city__name__icontains=location)
            )

        seller = self.request.query_params.get('seller')
        if seller:
            queryset = queryset.filter(seller_id=seller)
            
        return queryset.order_by(ordering)

    @action(detail=False, methods=['post'], permission_classes=[permissions.IsAdminUser])
    def recalculate_all_scores(self, request):
        """Force le recalcul des scores pour toutes les annonces actives."""
        posts = Post.objects.filter(is_active=True, is_delete=False)
        for post in posts:
            post.update_visibility_score()
        return Response({"message": f"Scores recalculés pour {posts.count()} annonces."})

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]

    def perform_create(self, serializer):
        # L'utilisateur connecté est automatiquement le vendeur
        serializer.save(seller=self.request.user)

    # 1. Action pour récupérer uniquement la corbeille de l'utilisateur
    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated])
    def trash(self, request):
        # On récupère uniquement les annonces supprimées de l'utilisateur connecté
        trash_posts = Post.objects.filter(seller=request.user, is_delete=True).order_by('-created_at')
        serializer = self.get_serializer(trash_posts, many=True)
        return Response(serializer.data)

    # 2. Action pour "supprimer" (envoyer à la corbeille) sans supprimer de la BDD
    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def soft_delete(self, request, pk=None):
        post = self.get_object()
        if post.seller != request.user:
            return Response({"error": "Action non autorisée"}, status=403)
        
        post.is_delete = True
        post.save()
        return Response({"message": "Annonce déplacée dans la corbeille"})

    # 3. Action pour restaurer une annonce
    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def restore(self, request, pk=None):
        # On cherche dans tous les objets (même supprimés) pour pouvoir restaurer
        post = Post.objects.get(pk=pk, seller=request.user)
        post.is_delete = False
        post.save()
        return Response({"message": "Annonce restaurée"})
    
    # 4. Action pour supprimer définitivement une annonce
    @action(detail=True, methods=['delete'], permission_classes=[permissions.IsAuthenticated])
    def hard_delete(self, request, pk=None):
        post = Post.objects.get(pk=pk, seller=request.user)
        post.delete()
        return Response({"message": "Annonce supprimée définitivement"})
        

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        
        viewed_posts = request.COOKIES.get('viewed_posts', '')
        viewed_ids = viewed_posts.split(',') if viewed_posts else []

        if str(instance.id) not in viewed_ids:
            # Mise à jour du compteur global
            instance.views_count += 1
            # Mise à jour du score de visibilité
            instance.update_visibility_score()
            instance.save(update_fields=['views_count', 'visibility_score', 'last_score_update'])
            
            # Mise à jour des stats journalières
            stat, created = PostViewStat.objects.get_or_create(
                post=instance,
                seller=instance.seller,
                date=now().date()
            )
            # Ici on peut garder F() car on ne renvoie pas 'stat' dans la réponse
            stat.views = F('views') + 1
            stat.save()

            viewed_ids.append(str(instance.id))

        # IMPORTANT : On recharge l'instance si on a utilisé F() ou modifié des champs
        # pour que le serializer ait les bonnes données numériques
        serializer = self.get_serializer(instance)
        response = Response(serializer.data)

        new_viewed_str = ','.join(viewed_ids)
        response.set_cookie(
            'viewed_posts', 
            new_viewed_str, 
            max_age=86400,
            httponly=True,
            samesite='Lax',
            secure=False
        )

        return response    


class DashboardStatsView(APIView):
    """
    Vue pour récupérer les statistiques du tableau de bord d'un vendeur.
    Retourne un résumé global et les données quotidiennes pour le graphique.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        today = now().date()
        user_posts = Post.objects.filter(seller=request.user, is_delete=False)

        # 1. Calcul des statistiques pour les cartes (Summary)
        # Vues totales cumulées sur tous les posts du vendeur
        total_views = user_posts.aggregate(total=Sum('views_count'))['total'] or 0
        
        # Vues spécifiquement enregistrées aujourd'hui dans PostViewStat
        today_views = PostViewStat.objects.filter(
            seller=request.user, 
            date=today
        ).aggregate(total=Sum('views'))['total'] or 0

        # Nombre d'annonces actuellement en ligne
        active_count = user_posts.filter(is_active=True).count()

        # Note moyenne (Exemple statique, à lier à votre modèle de Reviews si existant)
        avg_rating = 4.8 

        # 2. Préparation des données du graphique (30 derniers jours)
        start_date = today - timedelta(days=29)
        
        # Récupération des stats groupées par date
        daily_stats = PostViewStat.objects.filter(
            seller=request.user,
            date__range=[start_date, today]
        ).values('date').annotate(total_views=Sum('views')).order_by('date')

        # Conversion en dictionnaire pour un accès facile : {date: vues}
        stats_map = {stat['date']: stat['total_views'] for stat in daily_stats}
        
        # Génération de la liste complète pour le frontend (Recharts)
        chart_data = []
        for i in range(30):
            current_date = start_date + timedelta(days=i)
            chart_data.append({
                # Formatage de la date pour le frontend (ex: "24/04")
                "date": current_date.strftime("%d/%m"),
                "views": stats_map.get(current_date, 0)
            })

        # 3. Réponse finale structurée pour correspondre à Dashboard.tsx
        return Response({
            "summary": {
                "total_views": total_views,
                "today_views": today_views,
                "active_count": active_count,
                "avg_rating": avg_rating
            },
            "chart_data": chart_data
        })