from django.contrib.auth.models import AbstractUser
from django.db import models


class CustomUser(AbstractUser):
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('worker', 'Ishchi'),
        ('customer', 'Mijoz'),
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

    def __str__(self): return f"{self.name} ({self.produkt_type})"


# --- YANGI MODEL: OMBORXONA ---
class Lager(models.Model):
    menu_item = models.OneToOneField(MenuItem, on_delete=models.CASCADE, related_name='stock')
    current_stock = models.FloatField(default=0, verbose_name="Aktueller Lagerbestand (kg)")
    target_amount = models.FloatField(default=0, verbose_name="Soll-Bestand (kg)")

    def __str__(self):
        return f"Lager: {self.menu_item.name} | {self.current_stock}/{self.target_amount} kg"

class Order(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='orders')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

    def str(self):
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
    product_name = models.CharField(max_length=255)
    quantity = models.PositiveIntegerField()

    def __str__(self):
        return f"{self.product_name}: {self.quantity}"