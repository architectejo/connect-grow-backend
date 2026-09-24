from rest_framework import serializers
from .models import City, Commune, Category, Favorite, Post, PostImage

class CommuneSerializer(serializers.ModelSerializer):
    class Meta:
        model = Commune
        fields = ['id', 'name', 'city']  # On inclut la ville pour pouvoir filtrer côté frontend

class CitySerializer(serializers.ModelSerializer):
    # On inclut les communes à l'intérieur de la ville pour un chargement efficace
    communes = CommuneSerializer(many=True, read_only=True)

    class Meta:
        model = City
        fields = ['id', 'name', 'communes']

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'icon', 'slug']



class BusinessProfileSerializer(serializers.ModelSerializer):
    class Meta:
        from apps.accounts.models import BusinessProfile
        model = BusinessProfile
        fields = ['business_name', 'bio', 'logo', 'is_verified']

class SellerSerializer(serializers.ModelSerializer):
    business_profile = BusinessProfileSerializer(read_only=True)
    avg_rating = serializers.SerializerMethodField()

    class Meta:
        from apps.accounts.models import User
        model = User
        fields = ['id', 'full_name', 'photo', 'phone', 'user_type', 'business_profile', 'date_joined', 'avg_rating']

    def get_avg_rating(self, obj):
        from apps.interactions.models import Review
        from django.db.models import Avg
        avg = Review.objects.filter(post__seller=obj).aggregate(Avg('rating'))['rating__avg']
        return avg or 0.0


class PostImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = PostImage
        fields = ['id', 'image', 'order']


class PostSerializer(serializers.ModelSerializer):
    category_name = serializers.ReadOnlyField(source='category.name')
    commune_name = serializers.ReadOnlyField(source='commune.name')
    seller = SellerSerializer(read_only=True)
    seller_name = serializers.ReadOnlyField(source='seller.full_name')
    main_image = serializers.ImageField(required=False, allow_null=True)
    images = PostImageSerializer(many=True, read_only=True)
    visibility_rank = serializers.SerializerMethodField()
    is_favorited = serializers.SerializerMethodField()
    favorites_count = serializers.IntegerField(source='favorited_by.count', read_only=True)

    class Meta:
        model = Post
        fields = [
            'id', 'seller', 'seller_name', 'category', 'category_name',
            'commune', 'commune_name', 'post_type', 'title', 'description',
            'price', 'currency', 'condition', 'stock', 'is_price_negotiable',
            'is_exchangeable', 'main_image', 'images', 'views_count',
            'likes_count', 'created_at', 'visibility_score', 'visibility_rank',
            'is_favorited', 'favorites_count',
        ]
        read_only_fields = ['seller', 'views_count', 'likes_count', 'created_at', 'visibility_score']

    def get_visibility_rank(self, obj):
        score = obj.visibility_score or 0.0
        if score > 50: return "Elite"
        if score > 10: return "Standard"
        return "Faible"

    def get_is_favorited(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
        # Nécessite d'annoter/prefetch pour éviter le N+1 sur les listes (voir la vue).
        if hasattr(obj, 'is_favorited_by_user'):
            return obj.is_favorited_by_user
        return obj.favorited_by.filter(user=request.user).exists()


class FavoriteSerializer(serializers.ModelSerializer):
    post = PostSerializer(read_only=True)
    post_id = serializers.PrimaryKeyRelatedField(
        source='post', queryset=Post.objects.filter(is_delete=False), write_only=True,
    )

    class Meta:
        model = Favorite
        fields = ['id', 'post', 'post_id', 'created_at']
