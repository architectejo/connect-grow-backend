from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import DealViewSet

router = DefaultRouter()
router.register(r'deals', DealViewSet, basename='deal')

urlpatterns = [
    path('', include(router.urls)),
]
