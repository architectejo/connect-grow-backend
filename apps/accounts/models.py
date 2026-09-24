from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models

class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("L'adresse email est obligatoire")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(email, password, **extra_fields)

class User(AbstractBaseUser, PermissionsMixin):
    USER_TYPE_CHOICES = (
        ('PARTICULIER', 'Particulier'),
        ('ENTREPRISE', 'Entreprise / Artisan'),
    )

    email = models.EmailField(unique=True)
    photo = models.ImageField(upload_to='profile_photos/', null=True, blank=True)
    full_name = models.CharField(max_length=255)
    user_type = models.CharField(max_length=20, choices=USER_TYPE_CHOICES, default='PARTICULIER')
    
    # Liaison avec la localisation (Option A)
    # On met null=True pour permettre la création avant d'avoir configuré les villes
    ville = models.ForeignKey('marketplace.City', on_delete=models.SET_NULL, null=True, blank=True, default=1)
    commune = models.ForeignKey('marketplace.Commune', on_delete=models.SET_NULL, null=True, blank=True)
    
    phone = models.CharField(max_length=20, blank=True)
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
        return self.email

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