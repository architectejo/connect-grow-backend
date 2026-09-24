from rest_framework import serializers

from apps.interactions.models import ContactRequest

from .models import Deal


class DealSerializer(serializers.ModelSerializer):
    initiator_name = serializers.ReadOnlyField(source='initiator.full_name')
    counterparty_name = serializers.ReadOnlyField(source='counterparty.full_name')
    post_title = serializers.ReadOnlyField(source='post.title')

    class Meta:
        model = Deal
        fields = [
            'id', 'post', 'post_title', 'initiator', 'initiator_name',
            'counterparty', 'counterparty_name', 'status', 'created_at', 'confirmed_at',
        ]
        read_only_fields = ['initiator', 'status', 'created_at', 'confirmed_at']

    def validate(self, attrs):
        request = self.context['request']
        user = request.user
        post = attrs['post']
        counterparty = attrs['counterparty']

        if counterparty.id == user.id:
            raise serializers.ValidationError("Vous ne pouvez pas déclarer une affaire avec vous-même.")

        # CDC 3.7 : au MVP, la déclaration se fait depuis l'historique des contacts.
        contacted_user_ids = set(
            ContactRequest.objects.filter(post=post).values_list('sender_id', flat=True)
        )

        if post.seller_id == user.id:
            if counterparty.id not in contacted_user_ids:
                raise serializers.ValidationError(
                    "La contrepartie doit avoir contacté cette annonce."
                )
        else:
            if user.id not in contacted_user_ids:
                raise serializers.ValidationError(
                    "Vous devez avoir contacté cette annonce avant de déclarer une affaire."
                )
            if counterparty.id != post.seller_id:
                raise serializers.ValidationError(
                    "La contrepartie doit être le vendeur de l'annonce."
                )

        return attrs
