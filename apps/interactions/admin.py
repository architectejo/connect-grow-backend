from django.contrib import admin
from .models import Review, ContactRequest, ExchangeProposal

@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    # CDC 3.7 : un avis retiré par la modération (is_hidden) sort du calcul du
    # Trust Score — cocher/décocher ici déclenche le recalcul (apps.reputation.signals).
    list_display = ('post', 'user', 'reviewed_user', 'rating', 'is_hidden', 'created_at')
    list_filter = ('is_hidden', 'rating')
    search_fields = ('post__title', 'user__email', 'user__phone', 'content')

admin.site.register(ContactRequest)
admin.site.register(ExchangeProposal)