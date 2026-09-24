from django.contrib import admin
from .models import AuditLog, ForbiddenItem, Report, Sanction


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ('id', 'content_type', 'object_id', 'reason', 'status', 'assigned_to', 'created_at')
    list_filter = ('status', 'reason', 'content_type')
    search_fields = ('description', 'decision_notes')


@admin.register(Sanction)
class SanctionAdmin(admin.ModelAdmin):
    list_display = ('user', 'sanction_type', 'is_active', 'issued_by', 'starts_at', 'ends_at')
    list_filter = ('sanction_type', 'is_active')
    search_fields = ('user__email', 'user__phone', 'reason')


@admin.register(ForbiddenItem)
class ForbiddenItemAdmin(admin.ModelAdmin):
    list_display = ('keyword', 'category', 'added_by', 'created_at')
    search_fields = ('keyword',)


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'actor', 'action', 'content_type', 'object_id')
    list_filter = ('action',)
    search_fields = ('actor__email', 'details')
    readonly_fields = [f.name for f in AuditLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
