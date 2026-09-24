from django.contrib import admin
from .models import City, Commune, Category, Favorite, MarketplaceSettings, Post, PostImage

@admin.register(City)
class CityAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)

@admin.register(Commune)
class CommuneAdmin(admin.ModelAdmin):
    list_display = ('name', 'city')
    list_filter = ('city',)
    search_fields = ('name',)

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'icon')
    prepopulated_fields = {'slug': ('name',)} # Génère le slug automatiquement

class PostImageInline(admin.TabularInline):
    model = PostImage
    extra = 0

@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ('title', 'post_type', 'status', 'price', 'currency', 'seller', 'is_delete', 'expires_at')
    list_filter = ('post_type', 'status', 'category', 'commune', 'currency', 'is_delete')
    search_fields = ('title', 'description')
    inlines = [PostImageInline]

@admin.register(Favorite)
class FavoriteAdmin(admin.ModelAdmin):
    list_display = ('user', 'post', 'created_at')
    search_fields = ('user__email', 'user__phone', 'post__title')

@admin.register(MarketplaceSettings)
class MarketplaceSettingsAdmin(admin.ModelAdmin):
    list_display = ('expiration_days', 'trash_retention_days', 'expiring_soon_warning_days')

    def has_add_permission(self, request):
        return not MarketplaceSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False