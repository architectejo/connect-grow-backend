from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ForbiddenItemViewSet, ModerationDashboardView, ReportViewSet, SanctionViewSet

router = DefaultRouter()
router.register(r'reports', ReportViewSet, basename='report')
router.register(r'sanctions', SanctionViewSet, basename='sanction')
router.register(r'forbidden-items', ForbiddenItemViewSet, basename='forbidden-item')

urlpatterns = [
    path('dashboard/', ModerationDashboardView.as_view(), name='moderation_dashboard'),
    path('', include(router.urls)),
]
