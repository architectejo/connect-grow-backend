from django.db import models
from django.conf import settings

class Transaction(models.Model):
    STATUS_CHOICES = (
        ('PENDING', 'En attente de paiement'),
        ('HELD', 'Fonds bloqués (Séquestre)'),
        ('SHIPPED', 'Article expédié'),
        ('COMPLETED', 'Transaction terminée'),
        ('CANCELLED', 'Annulée / Remboursée'),
        ('DISPUTE', 'En litige'),
    )

    # Références
    buyer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='purchases')
    seller = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sales')
    post = models.ForeignKey('marketplace.Post', on_delete=models.PROTECT)

    # Détails financiers
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    laxpaie_reference = models.CharField(max_length=100, unique=True, null=True, blank=True)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Trans {self.id} - {self.status}"