from django.contrib import admin
from .models import Review, ContactRequest, ExchangeProposal

# Register your models here.
admin.site.register(Review)
admin.site.register(ContactRequest)
admin.site.register(ExchangeProposal)