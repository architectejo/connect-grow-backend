#!/bin/sh
set -e

# cron ne reçoit pas l'environnement du conteneur : on le fige une fois ici
# (les variables ne changent pas en cours de route dans ce déploiement), et
# chaque ligne du crontab le recharge avant d'invoquer manage.py (CDC 5.6).
printenv | grep -v -E '^(HOME|PWD|SHLVL|_)=' > /etc/environment

crontab /app/cron/crontab

exec cron -f
