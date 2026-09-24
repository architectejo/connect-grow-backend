from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CityViewSet, CategoryViewSet, FavoriteViewSet, PostViewSet, CommuneViewSet
from .stats_views import DashboardStatsView, PostStatsView

router = DefaultRouter()
router.register(r'cities', CityViewSet, basename='city')
router.register(r'communes', CommuneViewSet, basename='commune')
router.register(r'categories', CategoryViewSet, basename='category')
router.register(r'posts', PostViewSet, basename='post')
router.register(r'favorites', FavoriteViewSet, basename='favorite')

urlpatterns = [
    path('stats/dashboard/', DashboardStatsView.as_view(), name='dashboard_stats'),
    path('stats/post/<int:pk>/', PostStatsView.as_view(), name='post_stats'),
    path('', include(router.urls)),
]