"""
URL configuration for kartoshka_firma project.
"""
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from operations.views import (
    HomeView, SignupHTMLView, LoginHTMLView, logout_view, EditProfileView,
    AdminDashboardView, AllUsersView, AdminOrderListView, approve_user, reject_user,
    activate_worker, deactivate_worker, lager_view,
    MenuCreateView, MenuUpdateView,
    WorkerDashboardView, start_shift, end_shift, shift_history_view, worker_produce,
    CustomerDashboardView, CustomerOrdersView, CreateOrderHTMLView, AddItemsToOrderView, cancel_order_item,
    asset_links, delete_menu_item
)

urlpatterns = [
    # --- ASOSIY SAHIFALAR ---
    path('', HomeView.as_view(), name='home'),
    path('', include('pwa.urls')),
    path('admin/', admin.site.urls),
    path('api/', include('operations.urls')), # Agar API ishlatayotgan bo'lsangiz

    # --- AUTHENTICATION ---
    path('signup/', SignupHTMLView.as_view(), name='signup_html'),
    path('login/', LoginHTMLView.as_view(), name='login_html'),
    path('logout/', logout_view, name='logout'),
    path('profile/edit/', EditProfileView.as_view(), name='edit_profile'),

    # --- ADMIN ---
    path('dashboard/admin/', AdminDashboardView.as_view(), name='admin_dashboard'),
    path('dashboard/admin/users/', AllUsersView.as_view(), name='admin_users'),
    path('dashboard/admin/orders/', AdminOrderListView.as_view(), name='admin_orders'),

    # User boshqaruvi
    path('dashboard/admin/approve/<int:user_id>/', approve_user, name='approve_user'),
    path('dashboard/admin/reject/<int:user_id>/', reject_user, name='reject_user'),
    path('dashboard/admin/activate/<int:user_id>/', activate_worker, name='activate_worker'),
    path('dashboard/admin/deactivate/<int:user_id>/', deactivate_worker, name='deactivate_worker'),

    # Menyu boshqaruvi
    path('menu/create/', MenuCreateView.as_view(), name='menu_create'),
    path('menu/<int:pk>/edit/', MenuUpdateView.as_view(), name='menu_update'),
    path('menu/delete/<int:pk>/', delete_menu_item, name='delete_menu_item'),

    # Ombor (Lager) - Faqat ko'rish uchun (Limitlar yo'q)
    path('admin-dashboard/lager/', lager_view, name='admin_lager'),

    # --- WORKER (ISHCHI) ---
    path('dashboard/worker/', WorkerDashboardView.as_view(), name='worker_dashboard'),
    path('dashboard/worker/produce/', worker_produce, name='worker_produce'), # ✅ YANGI (Fertig tugmasi uchun)

    path('start-shift/', start_shift, name='start_shift'),
    path('end-shift/', end_shift, name='end_shift'),
    path('shift-history/', shift_history_view, name='shift_history'),

    # --- CUSTOMER (MIJOZ) ---
    path('dashboard/customer/', CustomerDashboardView.as_view(), name='customer_dashboard'),
    path('dashboard/customer/orders/', CustomerOrdersView.as_view(), name='customer_orders'),
    path('order/create/', CreateOrderHTMLView.as_view(), name='create_order'),
    path('order/<int:order_id>/add-items/', AddItemsToOrderView.as_view(), name='add_items_to_order'),
    path('cancel-item/<int:item_id>/', cancel_order_item, name='cancel_order_item'),

    # --- TIZIM ---
    path('.well-known/assetlinks.json', asset_links),
]
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)