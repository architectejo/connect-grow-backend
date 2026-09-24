from datetime import timedelta

from django.core.validators import MaxLengthValidator, MaxValueValidator, MinLengthValidator, MinValueValidator
from django.db import models
from django.conf import settings
from django.utils import timezone

class Review(models.Model):
    # L'annonce concernée par l'avis
    post = models.ForeignKey('marketplace.Post', on_delete=models.CASCADE, related_name='reviews')
    # L'auteur de l'avis
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='reviews_written')
    # La personne évaluée (CDC 3.7 : l'une des deux parties de l'affaire conclue).
    # Nullable uniquement pour les avis historiques créés avant ce champ (voir migration) ;
    # toujours requis pour un nouvel avis (apps.interactions.serializers.ReviewSerializer).
    reviewed_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, related_name='reviews_received',
    )
    # CDC 3.7 : un avis n'est possible qu'après une affaire conclue. Nullable pour ne pas
    # invalider les avis créés avant l'introduction de ce module (apps.reputation) ; la
    # création d'un nouvel avis sans affaire confirmée est refusée au niveau du serializer.
    deal = models.ForeignKey(
        'reputation.Deal', on_delete=models.CASCADE, null=True, blank=True, related_name='reviews',
    )

    # CDC 3.7 : commentaire de 10 à 500 caractères.
    content = models.TextField(validators=[MinLengthValidator(10), MaxLengthValidator(500)])
    rating = models.PositiveSmallIntegerField(
        default=5, validators=[MinValueValidator(1), MaxValueValidator(5)],
    )  # De 1 à 5 étoiles

    # Réponse publique de la personne évaluée
    reply_content = models.TextField(null=True, blank=True)
    reply_at = models.DateTimeField(null=True, blank=True)

    # CDC 3.7 : un avis retiré par la modération sort du calcul du Trust Score.
    is_hidden = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        # Un seul avis par partie et par affaire (CDC 3.7).
        unique_together = ('deal', 'user')

    def can_still_be_edited(self):
        # CDC 3.7 : l'avis est modifiable pendant 48 heures.
        return timezone.now() < self.created_at + timedelta(hours=48)

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