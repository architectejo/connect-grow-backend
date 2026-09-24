from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.decorators import action
from .models import Review, ContactRequest, ExchangeProposal, Conversation, Message, Notification
from .serializers import (
    ReviewSerializer, ContactRequestSerializer, ExchangeProposalSerializer,
    ConversationSerializer, MessageSerializer, NotificationSerializer
)


class ReviewViewSet(viewsets.ModelViewSet):
    queryset = Review.objects.all()
    serializer_class = ReviewSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]

    def perform_create(self, serializer):
        review = serializer.save(user=self.request.user)
        Notification.objects.create(
            user=review.reviewed_user,
            notification_type='COMMENT',
            title=f"Nouvel avis sur {review.post.title}",
            content=f"{self.request.user.full_name} a laissé un avis : {review.content[:50]}...",
            link=f"/post/{review.post.id}"
        )

    def get_queryset(self):
        queryset = Review.objects.all()
        # CDC 3.7 : un avis retiré par la modération n'est plus affiché dans les
        # listes publiques (mais reste consultable par son auteur ou un admin,
        # p. ex. pour voir/gérer son propre avis masqué).
        if self.action == 'list' and not (self.request.user.is_authenticated and self.request.user.is_staff):
            queryset = queryset.filter(is_hidden=False)
        post_id = self.request.query_params.get('post')
        if post_id:
            queryset = queryset.filter(post_id=post_id)
        return queryset.order_by('-created_at')

    def perform_destroy(self, instance):
        if instance.user == self.request.user:
            instance.delete()
        else:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Vous ne pouvez pas supprimer l'avis d'un autre utilisateur.")

    def perform_update(self, serializer):
        if serializer.instance.user == self.request.user:
            serializer.save()
        else:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Vous ne pouvez pas modifier l'avis d'un autre utilisateur.")

    @action(detail=True, methods=['post'])
    def reply(self, request, pk=None):
        review = self.get_object()
        if review.reviewed_user_id != request.user.id:
            return Response(
                {"error": "Seule la personne évaluée peut répondre à cet avis."},
                status=status.HTTP_403_FORBIDDEN,
            )
        
        reply_content = request.data.get('reply_content')
        if not reply_content:
            return Response({"error": "Le contenu de la réponse est requis."}, status=status.HTTP_400_BAD_REQUEST)
        
        from django.utils import timezone
        review.reply_content = reply_content
        review.reply_at = timezone.now()
        review.save()

        # Notification pour l'auteur de l'avis
        post_title = review.post.title if review.post else "une annonce supprimée"
        Notification.objects.create(
            user=review.user,
            notification_type='SYSTEM',
            title=f"Réponse à votre avis",
            content=f"{request.user.full_name} a répondu à votre avis sur {post_title}",
            link=f"/post/{review.post_id}" if review.post_id else "",
        )

        serializer = self.get_serializer(review)
        return Response(serializer.data)

class ContactRequestViewSet(viewsets.ModelViewSet):
    queryset = ContactRequest.objects.all()
    serializer_class = ContactRequestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        contact_request = serializer.save(sender=self.request.user)
        post = contact_request.post
        seller = post.seller
        
        # Trouver ou créer la conversation
        conversation, created = Conversation.objects.get_or_create(
            post=post,
        )
        if created:
            conversation.participants.add(self.request.user, seller)
        
        # Ajouter le message
        Message.objects.create(
            conversation=conversation,
            sender=self.request.user,
            content=contact_request.message
        )

        # Notification pour le vendeur
        Notification.objects.create(
            user=seller,
            notification_type='CONTACT',
            title=f"Nouvelle demande de contact",
            content=f"{self.request.user.full_name} vous a contacté pour {post.title}",
            link=f"/messages"
        )

class ExchangeProposalViewSet(viewsets.ModelViewSet):
    queryset = ExchangeProposal.objects.all()
    serializer_class = ExchangeProposalSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        proposal = serializer.save(sender=self.request.user)
        post = proposal.post
        seller = post.seller
        
        conversation, created = Conversation.objects.get_or_create(
            post=post,
        )
        if created:
            conversation.participants.add(self.request.user, seller)
        
        Message.objects.create(
            conversation=conversation,
            sender=self.request.user,
            content=f"[PROPOSITION D'ÉCHANGE] {proposal.message}"
        )

        # Notification pour le vendeur
        Notification.objects.create(
            user=seller,
            notification_type='EXCHANGE',
            title=f"Nouvelle proposition d'échange",
            content=f"{self.request.user.full_name} propose un échange pour {post.title}",
            link=f"/messages"
        )

class ConversationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ConversationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Conversation.objects.filter(participants=self.request.user).order_by('-updated_at')

class MessageViewSet(viewsets.ModelViewSet):
    serializer_class = MessageSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = Message.objects.filter(conversation__participants=self.request.user)
        conversation_id = self.request.query_params.get('conversation')
        if conversation_id:
            queryset = queryset.filter(conversation_id=conversation_id)
        return queryset.order_by('created_at')

    def perform_create(self, serializer):
        message = serializer.save(sender=self.request.user)
        message.conversation.save() # update_at

        # Notification pour l'autre participant
        other = message.conversation.participants.exclude(id=self.request.user.id).first()
        if other:
            Notification.objects.create(
                user=other,
                notification_type='MESSAGE',
                title=f"Nouveau message de {self.request.user.full_name}",
                content=message.content[:50],
                link=f"/messages"
            )

class NotificationViewSet(viewsets.ModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user).order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=False, methods=['post'])
    def mark_all_as_read(self, request):
        Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        return Response({'status': 'notifications marked as read'})