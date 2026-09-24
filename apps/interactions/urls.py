from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ReviewViewSet, ContactRequestViewSet, ExchangeProposalViewSet,
    ConversationViewSet, MessageViewSet, NotificationViewSet
)

router = DefaultRouter()
router.register(r'reviews', ReviewViewSet, basename='review')
router.register(r'contacts', ContactRequestViewSet, basename='contact')
router.register(r'exchanges', ExchangeProposalViewSet, basename='exchange')
router.register(r'conversations', ConversationViewSet, basename='conversation')
router.register(r'messages', MessageViewSet, basename='message')
router.register(r'notifications', NotificationViewSet, basename='notification')

urlpatterns = [
    path('', include(router.urls)),
]