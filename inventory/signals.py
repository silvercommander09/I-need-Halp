from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
from .models import Batch

@receiver(post_save, sender=Batch)
def check_expiration(sender, instance, created, **kwargs):
    if created:
        expiration_date = instance.expiration_date
        today = timezone.now().date()
        days_until_expiration = (expiration_date - today).days

        if days_until_expiration <= 30:
            subject = f'Medicine Expiration Alert - {instance.medicine.name}'
            message = f'''
            Medicine: {instance.medicine.name}
            Batch Number: {instance.batch_number}
            Expiration Date: {instance.expiration_date}
            Days until expiration: {days_until_expiration}
            Current Quantity: {instance.quantity}
            '''
            
            send_mail(
                subject,
                message,
                settings.EMAIL_HOST_USER,
                [settings.EMAIL_HOST_USER],  # Send to admin email
                fail_silently=False,
            )