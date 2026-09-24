from django.contrib import admin
from .models import BusinessProfile, KycDocument, OtpCode, User

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('email', 'phone', 'phone_verified', 'full_name', 'user_type', 'is_staff')
    list_filter = ('user_type', 'is_staff', 'phone_verified')
    search_fields = ('email', 'phone', 'full_name')

@admin.register(BusinessProfile)
class BusinessProfileAdmin(admin.ModelAdmin):
    list_display = ('business_name', 'user', 'is_verified')
    list_filter = ('is_verified',)
    filter_horizontal = ('categories',) # Interface pratique pour choisir plusieurs catégories

@admin.register(KycDocument)
class KycDocumentAdmin(admin.ModelAdmin):
    list_display = ('business_profile', 'document_type', 'status', 'reviewed_by', 'created_at')
    list_filter = ('status', 'document_type')
    search_fields = ('business_profile__business_name',)
    readonly_fields = ('created_at',)

@admin.register(OtpCode)
class OtpCodeAdmin(admin.ModelAdmin):
    list_display = ('phone', 'purpose', 'is_used', 'attempts', 'created_at', 'expires_at')
    list_filter = ('purpose', 'is_used')
    search_fields = ('phone',)
