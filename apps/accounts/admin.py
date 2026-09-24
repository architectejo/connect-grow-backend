from django.contrib import admin
from .models import User, BusinessProfile

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('email', 'full_name', 'user_type', 'is_staff')
    list_filter = ('user_type', 'is_staff')
    search_fields = ('email', 'full_name')

@admin.register(BusinessProfile)
class BusinessProfileAdmin(admin.ModelAdmin):
    list_display = ('business_name', 'user', 'is_verified')
    list_filter = ('is_verified',)
    filter_horizontal = ('categories',) # Interface pratique pour choisir plusieurs catégories