import uuid

from django.db.models import Exists, F, OuterRef, Q
from django.shortcuts import get_object_or_404
from django.utils.timezone import now
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status, viewsets, permissions
from .models import City, Category, Favorite, Post, PostImage, PostUniqueView, Commune, PostViewStat
from .serializers import (
    CategorySerializer,
    CitySerializer,
    CommuneSerializer,
    FavoriteSerializer,
    PostImageSerializer,
    PostSerializer,
)

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
        # On trie par le score de visibilité "Trust & Engage" par défaut
        ordering = self.request.query_params.get('ordering', '-visibility_score')
        if ordering not in ('-visibility_score', 'visibility_score', '-created_at', 'created_at', 'price', '-price'):
            ordering = '-visibility_score'

        # Par défaut (Marketplace), on ne montre que ce qui n'est pas supprimé et actif
        queryset = Post.objects.filter(is_active=True, is_delete=False)

        # Filtre pour récupérer les annonces de l'utilisateur connecté
        my_posts = self.request.query_params.get('my_posts')
        if my_posts == 'true' and self.request.user.is_authenticated:
            queryset = Post.objects.filter(seller=self.request.user, is_delete=False)
        else:
            # --- FILTRES DYNAMIQUES (CDC 3.2) ---
            search = self.request.query_params.get('search')
            category = self.request.query_params.get('category')
            location = self.request.query_params.get('location')
            city = self.request.query_params.get('city')
            commune = self.request.query_params.get('commune')
            currency = self.request.query_params.get('currency')
            condition = self.request.query_params.get('condition')
            is_exchangeable = self.request.query_params.get('is_exchangeable')
            price_min = self.request.query_params.get('price_min')
            price_max = self.request.query_params.get('price_max')

            if search:
                queryset = queryset.filter(Q(title__icontains=search) | Q(description__icontains=search))

            if category:
                queryset = queryset.filter(category_id=category)

            if location:
                queryset = queryset.filter(
                    Q(commune__name__icontains=location) |
                    Q(commune__city__name__icontains=location)
                )

            if city:
                queryset = queryset.filter(commune__city_id=city)

            if commune:
                queryset = queryset.filter(commune_id=commune)

            if currency in ('USD', 'CDF'):
                queryset = queryset.filter(currency=currency)

            if condition:
                queryset = queryset.filter(condition=condition)

            if is_exchangeable is not None:
                queryset = queryset.filter(is_exchangeable=is_exchangeable.lower() == 'true')

            if price_min:
                queryset = queryset.filter(price__gte=price_min)

            if price_max:
                queryset = queryset.filter(price__lte=price_max)

            seller = self.request.query_params.get('seller')
            if seller:
                queryset = queryset.filter(seller_id=seller)

        if self.request.user.is_authenticated:
            # Évite le N+1 de is_favorited sur les listes.
            queryset = queryset.annotate(
                is_favorited_by_user=Exists(
                    Favorite.objects.filter(user=self.request.user, post=OuterRef('pk'))
                )
            )

        return queryset.order_by(ordering)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context

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
        post.deleted_at = now()
        post.save()
        return Response({"message": "Annonce déplacée dans la corbeille"})

    # 3. Action pour restaurer une annonce
    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def restore(self, request, pk=None):
        # On cherche dans tous les objets (même supprimés) pour pouvoir restaurer
        post = Post.objects.get(pk=pk, seller=request.user)
        post.is_delete = False
        post.deleted_at = None
        post.save()
        return Response({"message": "Annonce restaurée"})

    # 4. Action pour supprimer définitivement une annonce
    @action(detail=True, methods=['delete'], permission_classes=[permissions.IsAuthenticated])
    def hard_delete(self, request, pk=None):
        post = Post.objects.get(pk=pk, seller=request.user)
        post.delete()
        return Response({"message": "Annonce supprimée définitivement"})

    # Cycle de vie (CDC 3.2, 3.9) : pause, reprise, vente, renouvellement.
    # Ces actions portent aussi sur des annonces inactives (en pause, expirées),
    # donc hors du queryset public par défaut : lookup direct, comme restore/hard_delete.
    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def pause(self, request, pk=None):
        post = get_object_or_404(Post, pk=pk)
        if post.seller != request.user:
            return Response({"error": "Action non autorisée"}, status=status.HTTP_403_FORBIDDEN)
        post.pause()
        return Response(self.get_serializer(post).data)

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def unpause(self, request, pk=None):
        post = get_object_or_404(Post, pk=pk)
        if post.seller != request.user:
            return Response({"error": "Action non autorisée"}, status=status.HTTP_403_FORBIDDEN)
        resumed = post.unpause()
        if not resumed:
            return Response(
                {"error": "Cette annonce a expiré. Renouvelez-la plutôt.", "status": post.status},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(self.get_serializer(post).data)

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def mark_sold(self, request, pk=None):
        post = get_object_or_404(Post, pk=pk)
        if post.seller != request.user:
            return Response({"error": "Action non autorisée"}, status=status.HTTP_403_FORBIDDEN)
        post.mark_sold()
        return Response(self.get_serializer(post).data)

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def renew(self, request, pk=None):
        post = get_object_or_404(Post, pk=pk)
        if post.seller != request.user:
            return Response({"error": "Action non autorisée"}, status=status.HTTP_403_FORBIDDEN)
        post.renew()
        return Response(self.get_serializer(post).data)

    # 5. Galerie de photos (CDC 3.2 : 1 à 8 photos par annonce, main_image comprise)
    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def images(self, request, pk=None):
        post = self.get_object()
        if post.seller != request.user:
            return Response({"error": "Action non autorisée"}, status=status.HTTP_403_FORBIDDEN)

        current_count = post.images.count() + 1  # + main_image
        uploaded = request.FILES.getlist('image')
        if not uploaded:
            return Response({"error": "Aucune image fournie."}, status=status.HTTP_400_BAD_REQUEST)
        if current_count + len(uploaded) > PostImage.MAX_IMAGES_PER_POST:
            return Response(
                {"error": f"Une annonce ne peut pas dépasser {PostImage.MAX_IMAGES_PER_POST} photos."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        created = [PostImage.objects.create(post=post, image=f) for f in uploaded]
        return Response(PostImageSerializer(created, many=True).data, status=status.HTTP_201_CREATED)

    @images.mapping.delete
    def delete_image(self, request, pk=None):
        post = self.get_object()
        if post.seller != request.user:
            return Response({"error": "Action non autorisée"}, status=status.HTTP_403_FORBIDDEN)

        image_id = request.query_params.get('image_id')
        deleted, _ = post.images.filter(pk=image_id).delete()
        if not deleted:
            return Response({"error": "Photo introuvable."}, status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)

    # 6. Partage externe (CDC 3.4) : simple compteur, alimente l'engagement (CDC 3.8).
    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def share(self, request, pk=None):
        post = self.get_object()
        post.shares_count = F('shares_count') + 1
        post.save(update_fields=['shares_count'])
        post.refresh_from_db(fields=['shares_count'])
        post.update_visibility_score()
        return Response({"shares_count": post.shares_count})

    # 7. Favoris (CDC 3.2)
    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def favorite(self, request, pk=None):
        post = self.get_object()
        favorite, created = Favorite.objects.get_or_create(user=request.user, post=post)
        if not created:
            favorite.delete()
            return Response({"favorited": False})
        return Response({"favorited": True})

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()

        # CDC 3.8 : une vue unique par jour et par utilisateur (ou empreinte anonyme),
        # garantie par une contrainte d'unicité en base plutôt qu'un simple cookie.
        anon_id = request.COOKIES.get('anon_id') or uuid.uuid4().hex
        viewer_key = PostUniqueView.build_viewer_key(request.user, anon_id)

        _, is_new_view = PostUniqueView.objects.get_or_create(
            post=instance, date=now().date(), viewer_key=viewer_key,
        )

        if is_new_view:
            instance.views_count += 1
            instance.update_visibility_score()
            instance.save(update_fields=['views_count', 'visibility_score', 'last_score_update'])

            stat, created = PostViewStat.objects.get_or_create(
                post=instance,
                seller=instance.seller,
                date=now().date()
            )
            # Ici on peut garder F() car on ne renvoie pas 'stat' dans la réponse
            stat.views = F('views') + 1
            stat.save()

        serializer = self.get_serializer(instance)
        response = Response(serializer.data)

        if not request.COOKIES.get('anon_id'):
            response.set_cookie(
                'anon_id', anon_id,
                max_age=365 * 86400,
                httponly=True,
                samesite='Lax',
                secure=False,
            )

        return response


class FavoriteViewSet(viewsets.ModelViewSet):
    """Liste personnelle des favoris de l'utilisateur connecté (CDC 3.2)."""

    serializer_class = FavoriteSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ['get', 'post', 'delete']

    def get_queryset(self):
        return Favorite.objects.filter(user=self.request.user).select_related('post')

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
