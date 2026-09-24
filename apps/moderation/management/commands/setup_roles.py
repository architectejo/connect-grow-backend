"""CDC 3.11 : rôles super-administrateur (is_superuser, déjà géré par Django),
administrateur et modérateur (Group + permissions Django). Idempotent :
peut être relancé sans effet de bord, notamment à chaque déploiement
(docker-entrypoint.sh), car les permissions des nouveaux modèles n'existent
pas encore au moment des migrations elles-mêmes (post_migrate ne les crée
qu'une fois toutes les migrations de la commande terminées)."""
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand

MODERATOR_PERMISSIONS = {
    'moderation.report': ['view', 'add', 'change'],
    'moderation.sanction': ['view', 'add'],
    'moderation.forbiddenitem': ['view'],
    'accounts.kycdocument': ['view', 'change'],
    'accounts.user': ['view'],
    'interactions.review': ['view', 'change'],
    'marketplace.post': ['view'],
}

# L'administrateur hérite de tout ce que peut faire un modérateur, plus la
# gestion des sanctions lourdes, des référentiels et des paramètres d'algorithme.
ADMINISTRATOR_EXTRA_PERMISSIONS = {
    'moderation.sanction': ['change', 'delete'],
    'moderation.forbiddenitem': ['add', 'change', 'delete'],
    'accounts.user': ['change'],
    'accounts.businessprofile': ['view', 'change'],
    'marketplace.category': ['add', 'change', 'delete'],
    'marketplace.city': ['add', 'change', 'delete'],
    'marketplace.commune': ['add', 'change', 'delete'],
    'ranking.rankingsettings': ['view', 'change'],
    'reputation.trustscoresettings': ['view', 'change'],
}


def _permissions_for(spec):
    permissions = []
    for label, actions in spec.items():
        app_label, model = label.split('.')
        for action in actions:
            codename = f'{action}_{model}'
            try:
                permissions.append(Permission.objects.get(content_type__app_label=app_label, codename=codename))
            except Permission.DoesNotExist:
                continue  # Modèle pas encore migré sur cet environnement : on l'ignore proprement.
    return permissions


class Command(BaseCommand):
    help = "Crée/actualise les groupes Modérateur et Administrateur (CDC 3.11)."

    def handle(self, *args, **options):
        moderator_perms = _permissions_for(MODERATOR_PERMISSIONS)
        moderator_group, _ = Group.objects.get_or_create(name='Modérateur')
        moderator_group.permissions.set(moderator_perms)

        admin_perms = moderator_perms + _permissions_for(ADMINISTRATOR_EXTRA_PERMISSIONS)
        admin_group, _ = Group.objects.get_or_create(name='Administrateur')
        admin_group.permissions.set(admin_perms)

        if options['verbosity'] > 0:
            self.stdout.write(self.style.SUCCESS(
                f"Rôles à jour : Modérateur ({len(moderator_perms)} permissions), "
                f"Administrateur ({len(admin_perms)} permissions)."
            ))
