from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum
from datetime import timedelta
from django.utils.timezone import now
from .models import PostViewStat, Post
from apps.interactions.models import ContactStat
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

        # CDC 3.9 : contacts reçus et taux de contact par annonce (agrégat CDC 5.6,
        # apps.interactions.management.commands.refresh_dashboard_aggregates).
        contacts_count = ContactStat.objects.filter(seller=request.user).aggregate(
            total=Sum('count')
        )['total'] or 0
        contact_rate = round(contacts_count / active_posts, 2) if active_posts else 0.0

        # CDC 3.7 : Trust Score bayésien (déjà mis en cache par apps.reputation),
        # jamais recalculé ici pour rester cohérent avec le profil public du vendeur.
        # Le nom de champ avg_rating est conservé (déjà consommé par le frontend),
        # mais la valeur vient désormais du Trust Score, plus de la moyenne brute.
        return Response({
            "history": history_data,
            "summary": {
                "total_views": total_views,
                "today_views": today_views,
                "active_posts": active_posts,
                "contacts_count": contacts_count,
                "contact_rate": contact_rate,
                "avg_rating": request.user.trust_score,
                "review_count": request.user.reviews_count,
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
