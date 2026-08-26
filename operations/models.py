import datetime
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone



class CustomUser(AbstractUser):
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('worker', 'Mitarbeiter'),
        ('customer', 'Kunde'),
    ]
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='customer')

    email=models.EmailField(unique=True)
    is_approved = models.BooleanField(default=False)  # ✅ admin tasdiqlashi kerak
    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"


class MenuItem(models.Model):
    POTATO_TYPE_CHOICES = [('Roh', 'Roh'), ('Gar', 'Gar')]
    name = models.CharField(max_length=100)
    produkt_type = models.CharField(max_length=10, choices=POTATO_TYPE_CHOICES)
    beschreibung = models.TextField(blank=True, null=True)
    verfügbar = models.BooleanField(default=True)

    class Meta:
        unique_together = ('name', 'produkt_type')

    def __str__(self): return f"{self.name} ({self.produkt_type})"


# --- YANGI MODEL: OMBORXONA ---
class Lager(models.Model):
    menu_item = models.OneToOneField(MenuItem, on_delete=models.CASCADE, related_name='stock')
    current_stock = models.FloatField(default=0, verbose_name="Aktueller Lagerbestand (kg)")

    def __str__(self):
        return f"{self.menu_item.name}: {self.current_stock} kg"


class Order(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='orders')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    pickup_time = models.TimeField(default=datetime.time(18, 0), null=True, blank=True, verbose_name="Abholzeit / Pickup Time")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Order {self.id} by {self.user.username}"



class OrderItem(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    order = models.ForeignKey(Order, on_delete=models.CASCADE, null=True, blank=True)
    menu_item = models.ForeignKey(MenuItem, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    shift = models.ForeignKey('Shift', on_delete=models.SET_NULL, null=True, blank=True, related_name='produced_items')
    def str(self):
        return f"{self.quantity} x {self.menu_item.name} (Order {self.order.id})"

from django.utils import timezone

class Shift(models.Model):
    worker = models.ForeignKey('operations.CustomUser', on_delete=models.CASCADE)
    start_time = models.DateTimeField(default=timezone.now)
    end_time = models.DateTimeField(null=True, blank=True)
    total_packages_done = models.PositiveIntegerField(default=0) # Smena davomidagi jami paketlar
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.worker.username} - {self.start_time.strftime('%d.%m %H:%M')}"



class ShiftReport(models.Model):
    shift = models.ForeignKey(Shift, on_delete=models.CASCADE, related_name='reports')
    product_name = models.CharField(max_length=100)

    product_type = models.CharField(max_length=20, default='Roh')

    quantity = models.FloatField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.product_name} ({self.product_type}) - {self.quantity}kg"


import datetime


class FactorySettings(models.Model):
    palettes_per_hour = models.FloatField(
        default=2.0,
        verbose_name="Paletten pro Stunde",
        help_text="Anzahl der produzierten Paletten pro Stunde (z.B. 2.0)"
    )
    kg_per_palette = models.FloatField(
        default=625.0,
        verbose_name="Gewicht pro Palette (kg)",
        help_text="Gewicht einer einzelnen Palette in kg (z.B. 625 kg)"
    )
    buro_working_start = models.TimeField(
        default=datetime.time(8, 0),
        verbose_name="Büro Arbeitsbeginn"
    )
    buro_working_end = models.TimeField(
        default=datetime.time(17, 0),
        verbose_name="Büro Arbeitsende"
    )
    production_working_start = models.TimeField(
        default=datetime.time(6, 0),
        verbose_name="Produktion Arbeitsbeginn"
    )
    production_working_end = models.TimeField(
        default=datetime.time(22, 0),
        verbose_name="Produktion Arbeitsende"
    )
    next_day_cutoff_time = models.TimeField(
        default=datetime.time(22, 0),
        verbose_name="Cut-off-Zeit für nächsten Tag",
        help_text="Bestellungen nach dieser Uhrzeit werden automatisch für den Folgetag eingeplant"
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Fabrikeinstellung"
        verbose_name_plural = "Fabrikeinstellungen"

    @property
    def cut_off_time(self) -> datetime.time:
        """Alias property for next_day_cutoff_time."""
        return self.next_day_cutoff_time

    @cut_off_time.setter
    def cut_off_time(self, value: datetime.time):
        self.next_day_cutoff_time = value

    @property
    def hourly_production_target_kg(self) -> float:
        """Dynamically calculates hourly production capacity (palettes_per_hour * kg_per_palette)."""
        return float(self.palettes_per_hour * self.kg_per_palette)

    @property
    def daily_production_target_kg(self) -> float:
        """Dynamically calculates 24h daily production capacity from hourly target."""
        return float(self.hourly_production_target_kg * 24.0)

    def save(self, *args, **kwargs):
        self.pk = 1
        if kwargs.get('force_insert') and FactorySettings.objects.filter(pk=1).exists():
            kwargs.pop('force_insert', None)
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass

    @classmethod
    def get_settings(cls):
        settings, _ = cls.objects.get_or_create(
            pk=1,
            defaults={
                'palettes_per_hour': 2.0,
                'kg_per_palette': 625.0,
                'buro_working_start': datetime.time(8, 0),
                'buro_working_end': datetime.time(17, 0),
                'production_working_start': datetime.time(6, 0),
                'production_working_end': datetime.time(22, 0),
                'next_day_cutoff_time': datetime.time(22, 0),
            }
        )
        return settings

    def __str__(self):
        return f"Fabrikeinstellungen ({self.palettes_per_hour} Pal/h à {self.kg_per_palette}kg = {self.hourly_production_target_kg} kg/h, 24h: {self.daily_production_target_kg} kg)"

