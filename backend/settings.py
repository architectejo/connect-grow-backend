"""
Django settings for backend project.
Version sécurisée pour la production et le développement.
"""

from pathlib import Path
import os
from datetime import timedelta
from dotenv import load_dotenv

# Charger les variables d'environnement depuis le fichier .env
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# --- SÉCURITÉ CRITIQUE ---
# Ne jamais stocker la clé secrète directement dans le code
SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-fallback-key-change-me')

# DEBUG doit être à False en production pour ne pas exposer la structure de la DB en cas d'erreur
DEBUG = os.getenv('DEBUG', 'False') == 'True'

# Restreindre les hôtes autorisés pour éviter les attaques par empoisonnement d'hôte HTTP
# ALLOWED_HOSTS='localhost,127.0.0.1,api.connecteplus.cd' dans .env pour la recette/prod
ALLOWED_HOSTS = [h.strip() for h in os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',') if h.strip()]


# --- DÉFINITION DES APPLICATIONS ---
INSTALLED_APPS = [
    'daphne', # Toujours en haut pour ASGI
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # Bibliothèques tierces
    'rest_framework',
    'rest_framework_simplejwt',
    'corsheaders',
    
    # Applications locales
    'apps.accounts',
    'apps.marketplace',
    'apps.payments',
    'apps.interactions',
    'apps.reputation',
    'apps.ranking',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware', # Doit être avant CommonMiddleware
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware', # Protection contre les attaques CSRF
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware', # Protection contre le Clickjacking
]

ROOT_URLCONF = 'backend.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

# --- CONFIGURATION REST FRAMEWORK & JWT ---
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.AllowAny',
    ],
    # Protection contre le brute-force : limitation du nombre de requêtes
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/day',
        'user': '1000/day',
        # CDC 4.2 : limitation du débit sur l'OTP (coût SMS, anti-brute-force).
        'otp': '5/hour',
    }
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=1), # Réduit pour plus de sécurité
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True, # Sécurité accrue : change le refresh token à chaque usage
    'BLACKLIST_AFTER_ROTATION': True,
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'AUTH_HEADER_TYPES': ('Bearer',),
}

# --- CONFIGURATION CORS ---
# En production, remplacez CORS_ALLOW_ALL_ORIGINS par une liste précise
CORS_ALLOW_ALL_ORIGINS = DEBUG 

# 1. Autoriser explicitement l'URL du frontend React
# CORS_ALLOWED_ORIGINS='https://connecteplus.cd,https://www.connecteplus.cd' dans .env en recette/prod
CORS_ALLOWED_ORIGINS = [
    o.strip() for o in os.getenv(
        'CORS_ALLOWED_ORIGINS', 'http://localhost:8080,http://127.0.0.1:8080'
    ).split(',') if o.strip()
]

# 2. Obligatoire pour withCredentials: true (cookies)
CORS_ALLOW_CREDENTIALS = True

# 3. Assure-toi que ces méthodes sont autorisées
CORS_ALLOW_METHODS = [
    "DELETE",
    "GET",
    "OPTIONS",
    "PATCH",
    "POST",
    "PUT",
]

# --- BASE DE DONNÉES & SÉCURITÉ ---
# L'utilisation de l'ORM Django protège déjà nativement contre les Injections SQL
#
# CDC 2.5 : SQLite en développement, MySQL 8+ (InnoDB, utf8mb4, mode SQL strict)
# en recette/CI et en production. Le moteur est choisi par DB_ENGINE dans .env
# ('sqlite' par défaut, 'mysql' en recette/CI/prod) — jamais codé en dur (2.5, 4.7).
if os.getenv('DB_ENGINE', 'sqlite') == 'mysql':
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.mysql',
            'NAME': os.getenv('DB_NAME', 'connecteplus'),
            'USER': os.getenv('DB_USER', 'connecteplus'),
            'PASSWORD': os.getenv('DB_PASSWORD', ''),
            'HOST': os.getenv('DB_HOST', 'localhost'),
            'PORT': os.getenv('DB_PORT', '3306'),
            'OPTIONS': {
                'charset': 'utf8mb4',
                # Mode SQL strict explicite (2.5) : pas de troncature silencieuse des données.
                'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
            },
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / os.getenv('DB_NAME', 'db.sqlite3'),
        }
    }

# Paramètres de sécurité avancés (pour HTTPS en production)
if not DEBUG:
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000 # 1 an
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_SSL_REDIRECT = True

# --- AUTRES CONFIGURATIONS ---
AUTH_USER_MODEL = 'accounts.User'
ASGI_APPLICATION = 'backend.asgi.application'

# CDC 5.5 : une seule instance Daphne avec channel layer en mémoire suffit tant qu'il n'y a
# qu'un serveur ; Redis ici sert de base de travail locale, RabbitMQ interviendra seulement
# au passage à plusieurs instances Daphne (channels_rabbitmq, à valider avant adoption).
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            "hosts": [(os.getenv('REDIS_HOST', '127.0.0.1'), int(os.getenv('REDIS_PORT', 6379)))],
        },
    },
}

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# CDC 4.2 / 5.8 : pièces KYC dans un espace privé, jamais sous MEDIA_ROOT (qui est
# servi publiquement par Nginx/le helper static() en dev). Accès uniquement via une
# vue authentifiée réservée aux administrateurs (apps.accounts).
KYC_PRIVATE_ROOT = BASE_DIR / 'private_media' / 'kyc'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'