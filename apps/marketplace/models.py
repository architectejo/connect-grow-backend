# apps/marketplace/models.py
from django.core.validators import MaxLengthValidator, MinLengthValidator
from django.db import models
from django.conf import settings
from django.utils import timezone

from .images import convert_to_webp


class City(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name
    
    class Meta:
        verbose_name = "Ville"
        verbose_name_plural = "Villes"

class Commune(models.Model):
    city = models.ForeignKey(City, on_delete=models.CASCADE, related_name='communes')
    name = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.name} ({self.city.name})"
    
    class Meta:
        unique_together = ('city', 'name')
        verbose_name = "Commune"

class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    icon = models.CharField(max_length=50, help_text="Nom de l'icône Lucide (ex: shopping-bag)", blank=True)
    slug = models.SlugField(max_length=100, unique=True, blank=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Catégorie"


class Post(models.Model):
    POST_TYPE_CHOICES = (
        ('PRODUIT', 'Produit Physique'),
        ('SERVICE', 'Prestation de Service'),
    )

    CONDITION_CHOICES = (
        ('NEUF', 'Neuf'),
        ('OCCASION', 'Occasion / Très bon état'),
        ('RECONDITIONNE', 'Reconditionné'),
    )

    CURRENCY_CHOICES = (
        ('USD', 'USD'),
        ('CDF', 'CDF'),
    )

    seller = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='posts')
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    commune = models.ForeignKey(Commune, on_delete=models.CASCADE)

    # Distinction Produit / Service
    post_type = models.CharField(max_length=10, choices=POST_TYPE_CHOICES, default='PRODUIT')

    # CDC 3.2 : titre 10-100 caractères, description 20-3000 caractères.
    title = models.CharField(
        max_length=100, validators=[MinLengthValidator(10), MaxLengthValidator(100)],
    )
    description = models.TextField(
        validators=[MinLengthValidator(20), MaxLengthValidator(3000)],
    )
    price = models.DecimalField(max_digits=10, decimal_places=2)
    # CDC 2.3 : prix en USD ou en CDF, au choix du vendeur.
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default='USD')

    # Champs spécifiques aux produits
    condition = models.CharField(max_length=20, choices=CONDITION_CHOICES, null=True, blank=True)
    stock = models.PositiveIntegerField(default=1, help_text="Quantité disponible (si produit)")

    # Champs spécifiques aux services (optionnel)
    is_price_negotiable = models.BooleanField(default=True, verbose_name="Prix discutable")

    # On a le prix fixe pour les services et l'échange
    is_exchangeable = models.BooleanField(default=True, verbose_name="Echangeable")

    # Champs de gestion corbeille (CDC 3.10)
    is_delete = models.BooleanField(default=False, null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    # Images et Stats
    main_image = models.ImageField(upload_to='posts/')
    views_count = models.PositiveIntegerField(default=0)
    likes_count = models.PositiveIntegerField(default=0) # Pour l'algo Trust & Engage
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Algorithme Trust & Engage
    visibility_score = models.FloatField(default=0.0)
    last_score_update = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if self.main_image:
            self.main_image = convert_to_webp(self.main_image)
        super().save(*args, **kwargs)

    def update_visibility_score(self):
        from django.utils.timezone import now
        from apps.interactions.models import Review
        from django.db.models import Avg

        # 1. Engagement : (views * 0.1) + (likes * 2) + (comments * 5)
        comments_count = self.reviews.count()
        engagement = (self.views_count * 0.1) + (self.likes_count * 2) + (comments_count * 5)

        # 2. Dégradation Temporelle : -10% toutes les 24h (0.9^nb_jours)
        delta = now() - self.created_at
        days_passed = delta.total_seconds() / 86400
        decay = 0.9 ** days_passed

        # 3. Multiplicateur de Confiance : (seller_avg_rating / 5) ou 0.7
        # Note moyenne globale du vendeur (sur toutes ses annonces)
        avg_rating = Review.objects.filter(post__seller=self.seller).aggregate(Avg('rating'))['rating__avg']
        
        multiplier = (avg_rating / 5.0) if avg_rating else 0.7
        
        # Calcul final
        self.visibility_score = float(engagement * decay * multiplier)
        self.last_score_update = now()
        self.save(update_fields=['visibility_score', 'last_score_update'])

    def __str__(self):
        return f"[{self.post_type}] {self.title}"
    
class PostViewStat(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='daily_stats')
    # On lie au vendeur pour faciliter les requêtes du Dashboard
    seller = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='business_stats')
    date = models.DateField(auto_now_add=True)
    views = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ('post', 'date')
        verbose_name = "Statistique de vue"
        ordering = ['-date']

    def __str__(self):
        return f"{self.post.title} - {self.date} ({self.views} vues)"


class PostImage(models.Model):
    """CDC 3.2 : une annonce porte de 1 à 8 photos (main_image compte pour la
    première ; ce modèle porte les photos supplémentaires de la galerie)."""

    MAX_IMAGES_PER_POST = 8

    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='posts/gallery/')
    order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', 'created_at']

    def save(self, *args, **kwargs):
        if self.image:
            self.image = convert_to_webp(self.image)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Photo de {self.post.title} (#{self.order})"


class Favorite(models.Model):
    """CDC 3.2 : liste personnelle des annonces favorites d'un utilisateur."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='favorites')
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='favorited_by')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'post')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user} ♥ {self.post.title}"