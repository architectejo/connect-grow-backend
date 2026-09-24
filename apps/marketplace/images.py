"""CDC 3.2 / 4.5 : les photos d'annonce sont compressées et converties en WebP
à l'envoi, pour rester légères sur des connexions 3G instables."""
import io

from django.core.files.base import ContentFile
from PIL import Image

WEBP_QUALITY = 80


def convert_to_webp(uploaded_file, quality=WEBP_QUALITY):
    """Convertit un fichier image uploadé en WebP et retourne un ContentFile prêt
    à être assigné à un ImageField. Aucun effet si le fichier est déjà en WebP."""
    name = getattr(uploaded_file, 'name', '') or ''
    if name.lower().endswith('.webp'):
        return uploaded_file

    image = Image.open(uploaded_file)
    if image.mode in ('RGBA', 'LA') or (image.mode == 'P' and 'transparency' in image.info):
        image = image.convert('RGBA')
    else:
        image = image.convert('RGB')

    buffer = io.BytesIO()
    image.save(buffer, format='WEBP', quality=quality)
    buffer.seek(0)

    base_name = name.rsplit('.', 1)[0] if name else 'image'
    return ContentFile(buffer.read(), name=f"{base_name}.webp")
