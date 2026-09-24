from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum, Avg
from datetime import timedelta
from django.utils.timezone import now
from .models import PostViewStat, Post
from apps.interactions.models import Review
from rest_framework.response import Response

class DashboardStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        today = now().date()
        last_30_days = today - timedelta(days=30)
        
        # 1. Graphique des 30 derniers jours (Historique)
        history_stats = PostViewStat.objects.filter(
            seller=request.user,
            date__gte=last_30_days
        ).values('date').annotate(views=Sum('views')).order_by('date')

        history_data = [
            {
                "day": s['date'].strftime('%d/%m'), 
                "views": s['views']
            } for s in history_stats
        ]
        
        # 2. Stats rapides (Résumé)
        total_views = PostViewStat.objects.filter(seller=request.user).aggregate(total=Sum('views'))['total'] or 0
        today_views = PostViewStat.objects.filter(seller=request.user, date=today).aggregate(today=Sum('views'))['today'] or 0
        active_posts = Post.objects.filter(seller=request.user, is_active=True, is_delete=False).count()
        
        # Note moyenne
        avg_rating = Review.objects.filter(post__seller=request.user).aggregate(avg=Avg('rating'))['avg'] or 0
        review_count = Review.objects.filter(post__seller=request.user).count()
        
        return Response({
            "history": history_data,
            "summary": {
                "total_views": total_views,
                "today_views": today_views,
                "active_posts": active_posts,
                "avg_rating": round(float(avg_rating), 1),
                "review_count": review_count
            }
        })

class PostStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        try:
            post = Post.objects.get(pk=pk, seller=request.user)
        except Post.DoesNotExist:
            return Response({"error": "Post not found or access denied"}, status=404)
        
        today = now().date()
        last_30_days = today - timedelta(days=30)
        
        history_stats = PostViewStat.objects.filter(
            post=post,
            date__gte=last_30_days
        ).order_by('date')

        history_data = [
            {
                "day": s.date.strftime('%d/%m'), 
                "views": s.views
            } for s in history_stats
        ]
        
        return Response({
            "history": history_data
        })