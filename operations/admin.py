from django.contrib import admin
from .models import CustomUser, MenuItem, Order, OrderItem, Shift, Lager
from django.db.models import Sum
from .utils import calculate_menu_totals

@admin.register(CustomUser)
class CustomUserAdmin(admin.ModelAdmin):
    list_display = ('username', 'role', 'email', 'is_staff')
    list_filter = ('role', 'is_staff')
    search_fields = ('username', 'email')

def calculate_menu_totals():
    """
    Har bir menyu uchun jami buyurtma qilingan miqdorni hisoblash.
    """
    return OrderItem.objects.values('menu_item').annotate(total_quantity=Sum('quantity'))

@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = ('name', 'verfügbar', 'get_total_quantity')
    list_filter = ('verfügbar',)
    search_fields = ('name',)

    def get_total_quantity(self, obj):
        totals = calculate_menu_totals()
        for total in totals:
            if total['menu_item'] == obj.id:
                return total['total_quantity']
        return 0

    get_total_quantity.short_description = "Menyu bo'yicha hisoblash"


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 1


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    inlines = [OrderItemInline]
    list_display = ['id', 'user', 'status', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['user__username']

@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ['id', 'order', 'menu_item', 'quantity',]
    list_filter = ['order']
    search_fields = ['order__user__username']

@admin.register(Shift)
class ShiftAdmin(admin.ModelAdmin):
    list_display = ('worker', 'start_time', 'end_time', 'total_packages_done', 'is_active')
    list_filter = ('is_active', 'worker')


@admin.register(Lager)
class LagerAdmin(admin.ModelAdmin):
    # 'updated_at'ni o'chirib tashladik, chunki u modelda yo'q ekan
    list_display = ('menu_item', 'current_stock')

    search_fields = ('menu_item__name',)
    list_filter = ('menu_item__produkt_type',)
    list_editable = ('current_stock',)
