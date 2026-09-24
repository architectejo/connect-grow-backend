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
    # CDC 3.8 : termes E de l'engagement. Pas encore alimentés (fonctions sociales P2 :
    # commentaires publics et partage externe), présents dès maintenant pour que la
    # formule de visibilité soit complète et ne demande pas de migration ultérieure.
    comments_count = models.PositiveIntegerField(default=0)
    shares_count = models.PositiveIntegerField(default=0)
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
        """CDC 3.8 : visibility_score = E . T . R . (1 + b)

        - E, engagement : 1 + ln(1 + w_v.vues + w_l.likes + w_c.commentaires + w_s.partages)
        - T, confiance : 0,8 + 0,4 . (TrustScore / 5), borné à [trust_factor_min, trust_factor_max]
        - R, récence : e^(-λ . âge_heures), avec une demi-vie paramétrable (72 h par défaut)
        - b, Boost : 0 tant que la billetterie (P3) n'existe pas

        R est calculé au moment de l'appel (aucun traitement de fond n'est requis, CDC 3.8) ;
        cette méthode elle-même est déclenchée par les signaux d'engagement (vue, like...) et
        par apps.reputation quand le Trust Score du vendeur change.
        """
        import math

        from django.utils.timezone import now

        from apps.ranking.models import RankingSettings

        settings_row = RankingSettings.get_solo()

        engagement_raw = (
            settings_row.weight_views * self.views_count
            + settings_row.weight_likes * self.likes_count
            + settings_row.weight_comments * self.comments_count
            + settings_row.weight_shares * self.shares_count
        )
        engagement = 1 + math.log(1 + engagement_raw)

        trust_factor = 0.8 + 0.4 * (self.seller.trust_score / 5.0)
        trust_factor = max(settings_row.trust_factor_min, min(settings_row.trust_factor_max, trust_factor))

        age_hours = (now() - self.created_at).total_seconds() / 3600
        decay_rate = math.log(2) / settings_row.recency_half_life_hours
        recency = math.exp(-decay_rate * age_hours)

        boost = 0  # CDC 7 : le Boost payant arrive en Phase 3.

        self.visibility_score = engagement * trust_factor * recency * (1 + boost)
        self.last_score_update = now()
        self.save(update_fields=['visibility_score', 'last_score_update'])

    def is_trending(self):
        """CDC 3.8 : badge « Tendance » sur forte hausse d'engagement sur 24 h.
        Le CDC ne fixe pas de seuil exact ; heuristique documentée ici, à ajuster
        avec le maître d'ouvrage : au moins 5 vues aujourd'hui, et au moins le
        double de la moyenne quotidienne des 7 jours précédents."""
        from datetime import timedelta

        today = timezone.now().date()
        week_ago = today - timedelta(days=7)
        previous_stats = list(self.daily_stats.filter(date__gte=week_ago, date__lt=today))
        if not previous_stats:
            return False

        avg_previous = sum(s.views for s in previous_stats) / len(previous_stats)
        today_stat = self.daily_stats.filter(date=today).first()
        today_views = today_stat.views if today_stat else 0

        return today_views >= 5 and avg_previous > 0 and today_views >= 2 * avg_previous

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


class PostUniqueView(models.Model):
    """CDC 3.8 : « une vue unique = une annonce vue par un utilisateur connecté
    (ou une empreinte anonyme) une fois par jour, garantie par une contrainte
    d'unicité en base. » viewer_key vaut "user:<id>" ou "anon:<empreinte>" :
    une seule colonne texte, jamais nulle, pour une contrainte unique portable
    SQLite/MySQL (2.6) — pas de contrainte d'unicité conditionnelle sur deux
    colonnes nullables alternatives."""

    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='unique_views')
    viewer_key = models.CharField(max_length=64)
    date = models.DateField(auto_now_add=True)

    class Meta:
        unique_together = ('post', 'date', 'viewer_key')

    @staticmethod
    def build_viewer_key(user, anon_fingerprint):
        if user is not None and user.is_authenticated:
            return f"user:{user.id}"
        return f"anon:{anon_fingerprint}"


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