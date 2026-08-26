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
    # MUHIM: 'current_stock' ham list_display, ham list_editable ichida bo'lishi shart
    list_display = ('menu_item', 'get_produkt_type', 'current_stock')

    search_fields = ('menu_item__name',)
    list_filter = ('menu_item__produkt_type',)

    # Ro'yxatning o'zida tahrirlash imkoniyati
    list_editable = ('current_stock',)

    @admin.display(description='Typ')
    def get_produkt_type(self, obj):
        return obj.menu_item.produkt_type

    # Admin panelda Lager obyektini tahrirlashda (Detail view) ko'rinadigan maydonlar
    fields = ('menu_item', 'current_stock')


from .models import FactorySettings

@admin.register(FactorySettings)
class FactorySettingsAdmin(admin.ModelAdmin):
    list_display = (
        '__str__',
        'palettes_per_hour',
        'kg_per_palette',
        'get_hourly_target_kg',
        'get_daily_target_kg',
        'next_day_cutoff_time',
        'updated_at'
    )
    fieldsets = (
        ('Produktionskapazität (Paletten & Gewicht)', {
            'fields': ('palettes_per_hour', 'kg_per_palette')
        }),
        ('Arbeitszeiten & Schichtzeiten', {
            'fields': (
                ('buro_working_start', 'buro_working_end'),
                ('production_working_start', 'production_working_end'),
                'next_day_cutoff_time'
            )
        }),
    )

    @admin.display(description="Stundenziel (kg/h)")
    def get_hourly_target_kg(self, obj):
        return f"{obj.hourly_production_target_kg:.0f} kg/h"

    @admin.display(description="24h-Tagesziel (kg)")
    def get_daily_target_kg(self, obj):
        return f"{obj.daily_production_target_kg:.0f} kg"

    def has_add_permission(self, request):
        return not FactorySettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

