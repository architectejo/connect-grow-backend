from rest_framework import serializers
from .models import Review, ContactRequest, ExchangeProposal, Conversation, Message, Notification


class ReviewSerializer(serializers.ModelSerializer):
    user_name = serializers.ReadOnlyField(source='user.full_name')
    user_id = serializers.ReadOnlyField(source='user.id')
    is_post_owner = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = [
            'id', 'post', 'user_id', 'user_name', 'content', 'rating', 
            'reply_content', 'reply_at', 'created_at', 'is_post_owner'
        ]
        read_only_fields = ['user', 'reply_at']

    def get_is_post_owner(self, obj):
        request = self.context.get('request')
        if request and request.user:
            return obj.post.seller == request.user
        return False

    def validate(self, data):
        # Si on est en train de créer (pas d'instance)
        if not self.instance:
            user = self.context['request'].user
            post = data.get('post')
            if post and Review.objects.filter(user=user, post=post).exists():
                raise serializers.ValidationError("Vous avez déjà laissé un avis sur cette annonce.")
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