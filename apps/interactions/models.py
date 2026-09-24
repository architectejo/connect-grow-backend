from django.db import models
from django.conf import settings

class Review(models.Model):
    # L'annonce concernée par l'avis
    post = models.ForeignKey('marketplace.Post', on_delete=models.CASCADE, related_name='reviews')
    # L'auteur de l'avis
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    
    content = models.TextField()
    rating = models.PositiveSmallIntegerField(default=5) # De 1 à 5 étoiles
    
    # Réponse du vendeur
    reply_content = models.TextField(null=True, blank=True)
    reply_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        # On peut empêcher un utilisateur de mettre plusieurs avis sur le même produit
        unique_together = ('post', 'user')

    def __str__(self):
        return f"Avis de {self.user.full_name} sur {self.post.title}"

class ContactRequest(models.Model):
    post = models.ForeignKey('marketplace.Post', on_delete=models.CASCADE, related_name='contact_requests')
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sent_contacts')
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Contact de {self.sender.full_name} pour {self.post.title}"

class ExchangeProposal(models.Model):
    post = models.ForeignKey('marketplace.Post', on_delete=models.CASCADE, related_name='exchange_proposals')
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sent_exchanges')
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Proposition d'échange de {self.sender.full_name} pour {self.post.title}"

class Conversation(models.Model):
    post = models.ForeignKey('marketplace.Post', on_delete=models.SET_NULL, null=True, related_name='conversations')
    participants = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='conversations')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"Conversation sur {self.post.title if self.post else 'objet supprimé'}"

class Message(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sent_messages')
    content = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Message de {self.sender.full_name} à {self.created_at}"

class Notification(models.Model):
    NOTIFICATION_TYPES = (
        ('COMMENT', 'Nouveau commentaire'),
        ('CONTACT', 'Demande de contact'),
        ('EXCHANGE', 'Proposition d\'échange'),
        ('MESSAGE', 'Nouveau message'),
        ('SYSTEM', 'Système'),
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES)
    title = models.CharField(max_length=255)
    content = models.TextField()
    link = models.CharField(max_length=255, null=True, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Notification pour {self.user.full_name} : {self.title}"