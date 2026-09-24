from rest_framework import serializers
from .models import Review, ContactRequest, ExchangeProposal, Conversation, Message, Notification


class ReviewSerializer(serializers.ModelSerializer):
    user_name = serializers.ReadOnlyField(source='user.full_name')
    user_id = serializers.ReadOnlyField(source='user.id')
    reviewed_user_id = serializers.ReadOnlyField(source='reviewed_user.id')
    is_post_owner = serializers.SerializerMethodField()
    can_edit = serializers.SerializerMethodField()
    # post est dérivé du deal côté serveur (voir validate) pour éviter toute
    # incohérence entre le post fourni par le client et celui de l'affaire.
    post = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Review
        fields = [
            'id', 'post', 'deal', 'user_id', 'user_name', 'reviewed_user_id', 'content', 'rating',
            'reply_content', 'reply_at', 'created_at', 'is_post_owner', 'can_edit',
        ]
        read_only_fields = ['user', 'reply_at']

    def get_is_post_owner(self, obj):
        request = self.context.get('request')
        if request and request.user:
            return obj.post.seller == request.user
        return False

    def get_can_edit(self, obj):
        request = self.context.get('request')
        if not request or obj.user_id != getattr(request.user, 'id', None):
            return False
        return obj.can_still_be_edited()

    def validate(self, data):
        from apps.reputation.models import Deal

        request = self.context['request']
        user = request.user

        if not self.instance:
            deal = data.get('deal')
            if deal is None:
                raise serializers.ValidationError(
                    {"deal": "Un avis n'est possible qu'après une affaire conclue."}
                )
            if deal.status != Deal.STATUS_CONFIRMED:
                raise serializers.ValidationError(
                    {"deal": "Cette affaire n'a pas encore été confirmée par les deux parties."}
                )
            reviewed_user = deal.other_party(user)
            if reviewed_user is None:
                raise serializers.ValidationError(
                    {"deal": "Vous ne faites pas partie de cette affaire."}
                )
            if Review.objects.filter(deal=deal, user=user).exists():
                raise serializers.ValidationError("Vous avez déjà laissé un avis pour cette affaire.")

            # CDC 3.7 : limite de 5 avis donnés par jour et par utilisateur.
            from django.utils import timezone
            today_count = Review.objects.filter(
                user=user, created_at__date=timezone.now().date(),
            ).count()
            if today_count >= 5:
                raise serializers.ValidationError(
                    "Vous avez atteint la limite de 5 avis par jour."
                )

            data['post'] = deal.post
            data['reviewed_user'] = reviewed_user
        else:
            if not self.instance.can_still_be_edited():
                raise serializers.ValidationError("L'avis n'est plus modifiable après 48 heures.")
            # L'affaire et la personne évaluée ne changent jamais après coup.
            data.pop('deal', None)

        return data

class ContactRequestSerializer(serializers.ModelSerializer):
    sender_name = serializers.ReadOnlyField(source='sender.full_name')

    class Meta:
        model = ContactRequest
        fields = ['id', 'post', 'sender', 'sender_name', 'message', 'created_at']
        read_only_fields = ['sender']

class ExchangeProposalSerializer(serializers.ModelSerializer):
    sender_name = serializers.ReadOnlyField(source='sender.full_name')

    class Meta:
        model = ExchangeProposal
        fields = ['id', 'post', 'sender', 'sender_name', 'message', 'created_at']
        read_only_fields = ['sender']

class MessageSerializer(serializers.ModelSerializer):
    sender_name = serializers.ReadOnlyField(source='sender.full_name')
    is_me = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = ['id', 'conversation', 'sender', 'sender_name', 'content', 'is_read', 'created_at', 'is_me']
        read_only_fields = ['sender']

    def get_is_me(self, obj):
        request = self.context.get('request')
        if request and request.user:
            return obj.sender == request.user
        return False

class ConversationSerializer(serializers.ModelSerializer):
    last_message = serializers.SerializerMethodField()
    other_participant = serializers.SerializerMethodField()
    post_title = serializers.ReadOnlyField(source='post.title')
    post_image = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = ['id', 'post', 'post_title', 'post_image', 'other_participant', 'last_message', 'updated_at']

    def get_last_message(self, obj):
        last_msg = obj.messages.last()
        if last_msg:
            return {
                'content': last_msg.content,
                'created_at': last_msg.created_at,
                'is_read': last_msg.is_read,
                'sender_id': last_msg.sender_id
            }
        return None

    def get_other_participant(self, obj):
        request = self.context.get('request')
        if request and request.user:
            other = obj.participants.exclude(id=request.user.id).first()
            if other:
                return {
                    'id': other.id,
                    'full_name': other.full_name,
                    'photo': other.photo.url if other.photo else None
                }
        return None
    
    def get_post_image(self, obj):
        if obj.post and obj.post.main_image:
            return obj.post.main_image.url
        return None

class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = '__all__'
        read_only_fields = ['user']