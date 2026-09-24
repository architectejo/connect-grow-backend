from django.contrib import admin
from .models import City, Commune, Category, Favorite, Post, PostImage

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
    list_display = ('title', 'post_type', 'price', 'currency', 'seller', 'is_delete', 'created_at')
    list_filter = ('post_type', 'category', 'commune', 'currency', 'is_delete')
    search_fields = ('title', 'description')
    inlines = [PostImageInline]

@admin.register(Favorite)
class FavoriteAdmin(admin.ModelAdmin):
    list_display = ('user', 'post', 'created_at')
    search_fields = ('user__email', 'user__phone', 'post__title')