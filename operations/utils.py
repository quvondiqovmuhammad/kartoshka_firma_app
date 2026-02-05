from django.db.models import Sum


def calculate_menu_totals():
    """Barcha Orderitemlarni menyu bo'yicha jami miqdorini hisoblaydi"""
    from operations.models import OrderItem
    menu_totals=OrderItem.objects.values('menu_item').annotate(total_quantity=Sum('quantity'))
    return menu_totals


def auto_complete_order_if_no_pending(order):
    # 'items' o'rniga 'orderitem_set' ishlatamiz
    all_items = order.orderitem_set.all()

    # Agar bitta ham 'pending' (kutilayotgan) mahsulot qolmagan bo'lsa
    if not all_items.filter(status='pending').exists():
        # Kamida bittasi 'completed' (bajarilgan) bo'lsa - STATUS YASHIL (completed)
        if all_items.filter(status='completed').exists():
            order.status = 'completed'
        else:
            # Agar hamma mahsulot bekor qilingan bo'lsa - STATUS QIZIL (cancelled)
            order.status = 'cancelled'
        order.save()

