from django.db.models import Q
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Deal
from .serializers import DealSerializer


class DealViewSet(viewsets.ModelViewSet):
    """CDC 3.7 : déclaration et confirmation d'une affaire conclue."""

    serializer_class = DealSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ['get', 'post', 'head', 'options']

    def get_queryset(self):
        user = self.request.user
        return Deal.objects.filter(Q(initiator=user) | Q(counterparty=user)).select_related('post')

    def perform_create(self, serializer):
        serializer.save(initiator=self.request.user)

    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        deal = self.get_object()
        if deal.counterparty_id != request.user.id:
            return Response(
                {"error": "Seule la contrepartie peut confirmer cette affaire."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if deal.status != Deal.STATUS_PENDING:
            return Response({"error": "Cette affaire n'est plus en attente."}, status=status.HTTP_400_BAD_REQUEST)
        deal.confirm()
        return Response(DealSerializer(deal).data)

    @action(detail=True, methods=['post'])
    def decline(self, request, pk=None):
        deal = self.get_object()
        if deal.counterparty_id != request.user.id:
            return Response(
                {"error": "Seule la contrepartie peut refuser cette affaire."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if deal.status != Deal.STATUS_PENDING:
            return Response({"error": "Cette affaire n'est plus en attente."}, status=status.HTTP_400_BAD_REQUEST)
        deal.decline()
        return Response(DealSerializer(deal).data)
