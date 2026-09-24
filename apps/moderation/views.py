from rest_framework import generics, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import AuditLog, ForbiddenItem, Report, Sanction
from .serializers import ForbiddenItemSerializer, ReportSerializer, SanctionSerializer


def is_administrator(user):
    return user.is_superuser or user.groups.filter(name='Administrateur').exists()


class ReportViewSet(viewsets.ModelViewSet):
    """CDC 3.11 : file unique de signalements, prise en charge, décision."""

    serializer_class = ReportSerializer
    http_method_names = ['get', 'post', 'head', 'options']

    def get_permissions(self):
        if self.action == 'create':
            return [permissions.IsAuthenticated()]
        return [permissions.IsAdminUser()]

    def get_queryset(self):
        queryset = Report.objects.select_related('reporter', 'assigned_to', 'content_type')
        status_param = self.request.query_params.get('status')
        if status_param:
            queryset = queryset.filter(status=status_param)
        return queryset

    def perform_create(self, serializer):
        serializer.save(reporter=self.request.user)

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAdminUser])
    def claim(self, request, pk=None):
        report = self.get_object()
        report.claim(request.user)
        AuditLog.record(request.user, 'REPORT_CLAIMED', target=report)
        return Response(ReportSerializer(report).data)

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAdminUser])
    def resolve(self, request, pk=None):
        report = self.get_object()
        notes = request.data.get('notes', '')
        report.resolve(notes=notes)
        AuditLog.record(request.user, 'REPORT_RESOLVED', target=report, details=notes)
        return Response(ReportSerializer(report).data)

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAdminUser])
    def reject(self, request, pk=None):
        report = self.get_object()
        notes = request.data.get('notes', '')
        report.reject(notes=notes)
        AuditLog.record(request.user, 'REPORT_REJECTED', target=report, details=notes)
        return Response(ReportSerializer(report).data)


class SanctionViewSet(viewsets.ModelViewSet):
    """CDC 3.11 : avertissement, masquage d'annonce, suspension, bannissement."""

    serializer_class = SanctionSerializer
    permission_classes = [permissions.IsAdminUser]
    http_method_names = ['get', 'post', 'head', 'options']
    queryset = Sanction.objects.select_related('user', 'issued_by', 'related_post')

    def perform_create(self, serializer):
        sanction_type = serializer.validated_data.get('sanction_type')
        user = self.request.user
        if sanction_type not in Sanction.MODERATOR_ALLOWED_TYPES and not is_administrator(user):
            raise PermissionDenied(
                "Seul un administrateur peut prononcer une suspension ou un bannissement."
            )
        sanction = serializer.save(issued_by=user)
        sanction.apply()

        from apps.interactions.models import Notification
        Notification.objects.create(
            user=sanction.user,
            notification_type='SYSTEM',
            title="Sanction appliquée à votre compte",
            content=f"{sanction.get_sanction_type_display()} : {sanction.reason[:100]}",
        )

        AuditLog.record(user, f'SANCTION_{sanction_type}', target=sanction, details=sanction.reason)

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAdminUser])
    def lift(self, request, pk=None):
        sanction = self.get_object()
        if not sanction.is_active:
            return Response({"error": "Cette sanction n'est plus active."}, status=status.HTTP_400_BAD_REQUEST)
        sanction.lift()
        AuditLog.record(request.user, 'SANCTION_LIFTED', target=sanction)
        return Response(SanctionSerializer(sanction).data)


class ForbiddenItemViewSet(viewsets.ModelViewSet):
    """CDC 2.1 / 3.11 : référentiel des produits et services interdits."""

    serializer_class = ForbiddenItemSerializer
    queryset = ForbiddenItem.objects.all()

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [permissions.AllowAny()]
        return [permissions.IsAdminUser()]

    def perform_create(self, serializer):
        serializer.save(added_by=self.request.user)


class ModerationDashboardView(APIView):
    """CDC 3.11 : tableau de bord (utilisateurs, annonces, signalements en
    attente). Les revenus (P3) ne sont pas encore pertinents."""

    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        from apps.accounts.models import KycDocument, User
        from apps.marketplace.models import Post

        return Response({
            'users_count': User.objects.count(),
            'active_posts_count': Post.objects.filter(is_active=True, is_delete=False).count(),
            'pending_reports_count': Report.objects.filter(status=Report.STATUS_EN_ATTENTE).count(),
            'pending_kyc_count': KycDocument.objects.filter(status=KycDocument.STATUS_EN_ATTENTE).count(),
        })
