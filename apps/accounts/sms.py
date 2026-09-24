"""Passerelle SMS pour l'envoi des codes OTP (CDC 2.4, 3.1).

Le fournisseur SMS n'est pas encore retenu (CDC 2.4, hypothèse de lancement).
Cette fonction est le seul point d'appel du reste du code vers l'envoi de SMS :
brancher un fournisseur réel (Twilio, Africa's Talking, etc.) ne touche que ce
fichier. En développement, le code est simplement journalisé.
"""
import logging

from django.conf import settings

logger = logging.getLogger('apps.accounts.sms')


def send_otp_sms(phone: str, code: str, purpose: str) -> None:
    if settings.DEBUG:
        logger.info("[OTP DEV] %s pour %s (%s)", code, phone, purpose)
        return
    raise NotImplementedError(
        "Aucun fournisseur SMS configuré. Brancher le fournisseur retenu (CDC 2.4) ici."
    )
