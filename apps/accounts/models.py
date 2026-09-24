import random
from datetime import timedelta

from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.core.files.storage import FileSystemStorage
from django.core.validators import RegexValidator
from django.db import models
from django.conf import settings
from django.utils import timezone

# CDC 2.3 : numéros togolais... congolais au format +243 suivi de 9 chiffres.
phone_validator = RegexValidator(
    regex=r'^\+243\d{9}$',
    message="Le numéro doit être au format +243 suivi de 9 chiffres.",
)

# CDC 4.2 / 5.8 : les pièces KYC sont stockées dans un espace privé, jamais servi
# par le MEDIA_URL public. Ce dossier est en dehors de MEDIA_ROOT.
#
# Sous-classe (plutôt qu'une instance FileSystemStorage(location=...) directe) pour
# que la migration ne fige pas un chemin absolu propre à une machine : deconstruct()
# ne sérialise que "KycPrivateStorage()", et location est recalculé à chaque exécution
# depuis settings.KYC_PRIVATE_ROOT (donc correct en dev Windows comme dans le conteneur).
class KycPrivateStorage(FileSystemStorage):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('location', str(settings.KYC_PRIVATE_ROOT))
        kwargs.setdefault('base_url', None)
        super().__init__(*args, **kwargs)


kyc_storage = KycPrivateStorage()


class UserManager(BaseUserManager):
    def create_user(self, email=None, phone=None, password=None, **extra_fields):
        if not email and not phone:
            raise ValueError("Un email ou un numéro de téléphone est obligatoire")
        if email:
            email = self.normalize_email(email)
        user = self.model(email=email, phone=phone, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(email=email, password=password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    USER_TYPE_CHOICES = (
        ('PARTICULIER', 'Particulier'),
        ('ENTREPRISE', 'Entreprise / Artisan'),
    )

    # CDC 3.1 : inscription par téléphone OU par e-mail. Les deux sont donc
    # facultatifs individuellement (contrainte "au moins un des deux" gérée par
    # UserManager.create_user), mais chacun reste unique quand il est renseigné.
    # unique=True + null=True est portable SQLite/MySQL (2.6) : NULL n'est jamais
    # comparé égal à NULL par un index unique, donc plusieurs comptes sans email
    # ou sans téléphone cohabitent sans conflit.
    email = models.EmailField(unique=True, null=True, blank=True, default=None)
    phone = models.CharField(
        max_length=20, unique=True, null=True, blank=True, default=None,
        validators=[phone_validator],
    )
    phone_verified = models.BooleanField(default=False)

    photo = models.ImageField(upload_to='profile_photos/', null=True, blank=True)
    full_name = models.CharField(max_length=255)
    user_type = models.CharField(max_length=20, choices=USER_TYPE_CHOICES, default='PARTICULIER')

    # Liaison avec la localisation (Option A)
    # On met null=True pour permettre la création avant d'avoir configuré les villes
    ville = models.ForeignKey('marketplace.City', on_delete=models.SET_NULL, null=True, blank=True)
    commune = models.ForeignKey('marketplace.Commune', on_delete=models.SET_NULL, null=True, blank=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['full_name']

    groups = models.ManyToManyField(
        'auth.Group',
        related_name='custom_user_groups', # Nom unique
        blank=True,
        help_text='The groups this user belongs to.',
        verbose_name='groups',
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        related_name='custom_user_permissions', # Nom unique
        blank=True,
        help_text='Specific permissions for this user.',
        verbose_name='user permissions',
    )

    def __str__(self):
        return self.email or self.phone or f"Utilisateur #{self.pk}"


class BusinessProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='business_profile')
    business_name = models.CharField(max_length=255)
    # Relation Many-to-Many pour permettre plusieurs catégories par entreprise
    categories = models.ManyToManyField('marketplace.Category', blank=True)
    bio = models.TextField(blank=True)
    logo = models.ImageField(upload_to='business_logos/', null=True, blank=True)
    is_verified = models.BooleanField(default=False)
    nif = models.CharField(max_length=50, blank=True) # Pour le côté pro client

    def __str__(self):
        return self.business_name


class OtpCode(models.Model):
    """CDC 3.1 : OTP SMS à 6 chiffres, valable 10 minutes, 3 tentatives maximum."""

    PURPOSE_REGISTER = 'REGISTER'
    PURPOSE_LOGIN = 'LOGIN'
    PURPOSE_PASSWORD_RESET = 'PASSWORD_RESET'
    PURPOSE_CHOICES = (
        (PURPOSE_REGISTER, "Inscription"),
        (PURPOSE_LOGIN, "Connexion"),
        (PURPOSE_PASSWORD_RESET, "Réinitialisation du mot de passe"),
    )

    VALIDITY_MINUTES = 10
    MAX_ATTEMPTS = 3
    CODE_LENGTH = 6

    phone = models.CharField(max_length=20, validators=[phone_validator])
    purpose = models.CharField(max_length=20, choices=PURPOSE_CHOICES)
    code_hash = models.CharField(max_length=128)
    attempts = models.PositiveSmallIntegerField(default=0)
    is_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        indexes = [models.Index(fields=['phone', 'purpose', 'is_used'])]
        ordering = ['-created_at']

    @classmethod
    def issue(cls, phone, purpose):
        """Génère un nouveau code, invalide les codes précédents non utilisés
        pour ce couple (phone, purpose), et retourne (instance, code_en_clair)."""
        cls.objects.filter(phone=phone, purpose=purpose, is_used=False).update(is_used=True)
        code = ''.join(random.choices('0123456789', k=cls.CODE_LENGTH))
        instance = cls.objects.create(
            phone=phone,
            purpose=purpose,
            code_hash=make_password(code),
            expires_at=timezone.now() + timedelta(minutes=cls.VALIDITY_MINUTES),
        )
        return instance, code

    def is_expired(self):
        return timezone.now() >= self.expires_at

    def verify(self, raw_code):
        """Vérifie le code fourni. Incrémente les tentatives à chaque échec.
        Retourne True seulement si le code est valide, non expiré, non utilisé
        et sous la limite de tentatives ; marque le code comme utilisé si OK."""
        if self.is_used or self.is_expired() or self.attempts >= self.MAX_ATTEMPTS:
            return False
        if not check_password(raw_code, self.code_hash):
            self.attempts += 1
            self.save(update_fields=['attempts'])
            return False
        self.is_used = True
        self.save(update_fields=['is_used'])
        return True

    def __str__(self):
        return f"OTP {self.purpose} pour {self.phone}"


class KycDocument(models.Model):
    """CDC 3.1 / 3.11 : pièces justificatives KYC d'un Profil Business,
    en file d'attente de validation par la modération."""

    DOC_RCCM = 'RCCM'
    DOC_ID_NATIONALE = 'ID_NATIONALE'
    DOC_PIECE_GERANT = 'PIECE_GERANT'
    DOC_TYPE_CHOICES = (
        (DOC_RCCM, "RCCM"),
        (DOC_ID_NATIONALE, "Identification nationale"),
        (DOC_PIECE_GERANT, "Pièce d'identité du gérant"),
    )

    STATUS_EN_ATTENTE = 'EN_ATTENTE'
    STATUS_VALIDE = 'VALIDE'
    STATUS_REFUSE = 'REFUSE'
    STATUS_CHOICES = (
        (STATUS_EN_ATTENTE, "En attente"),
        (STATUS_VALIDE, "Validé"),
        (STATUS_REFUSE, "Refusé"),
    )

    business_profile = models.ForeignKey(
        BusinessProfile, on_delete=models.CASCADE, related_name='kyc_documents',
    )
    document_type = models.CharField(max_length=20, choices=DOC_TYPE_CHOICES)
    file = models.FileField(upload_to='', storage=kyc_storage)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_EN_ATTENTE)
    rejection_reason = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='kyc_reviews',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_document_type_display()} — {self.business_profile.business_name} ({self.status})"
