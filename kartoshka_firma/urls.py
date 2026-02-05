"""
URL configuration for kartoshka_firma project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path,include

from operations.views import HomeView, SignupHTMLView, LoginHTMLView, AdminDashboardView, WorkerDashboardView, \
    CustomerDashboardView, MenuCreateView, CreateOrderHTMLView, AddItemsToOrderView, CustomerOrdersView, \
    complete_product_view, logout_view, reset_all_completed, cancel_order_item, MenuUpdateView, AdminOrderListView, \
    EditProfileView, AllUsersView, approve_user, reject_user, deactivate_worker, activate_worker, start_shift, \
    end_shift, shift_history_view, asset_links, lager_view, refill_lager, update_target, LagerRefillView

urlpatterns = [
    path('', HomeView.as_view(), name='home'),
    path('', include('pwa.urls')),
    path('admin/', admin.site.urls),
    path('signup/', SignupHTMLView.as_view(), name='signup_html'),  # HTML forma
    path('login/', LoginHTMLView.as_view(), name='login_html'),
    path('logout/', logout_view, name='logout'),
    path('api/',include('operations.urls')),
    path('dashboard/admin/users/', AllUsersView.as_view(), name='admin_users'),
    path('dashboard/admin/approve/<int:user_id>/', approve_user, name='approve_user'),
    path('dashboard/admin/reject/<int:user_id>/', reject_user, name='reject_user'),
    path('profile/edit/', EditProfileView.as_view(), name='edit_profile'),
    path('dashboard/admin/', AdminDashboardView.as_view(), name='admin_dashboard'),
    path('dashboard/admin/orders/', AdminOrderListView.as_view(), name='admin_orders'),
    path('menu/create/', MenuCreateView.as_view(), name='menu_create'),
    path('menu/<int:pk>/edit/', MenuUpdateView.as_view(), name='menu_update'),
    path('dashboard/worker/', WorkerDashboardView.as_view(), name='worker_dashboard'),
    path('dashboard/worker/complete/<int:menu_item_id>/', complete_product_view, name='complete_product'),
    path('dashboard/worker/reset/', reset_all_completed, name='reset_all_completed'),
    path('dashboard/customer/', CustomerDashboardView.as_view(), name='customer_dashboard'),
    path('dashboard/customer/orders/', CustomerOrdersView.as_view(), name='customer_orders'),
    path('order/create/', CreateOrderHTMLView.as_view(), name='create_order'),
    path('order/<int:order_id>/add-items/', AddItemsToOrderView.as_view(), name='add_items_to_order'),
    path('cancel-item/<int:item_id>/', cancel_order_item, name='cancel_order_item'),
    path('dashboard/admin/deactivate/<int:user_id>/', deactivate_worker, name='deactivate_worker'),
    path('dashboard/admin/activate/<int:user_id>/', activate_worker, name='activate_worker'),
    path('start-shift/', start_shift, name='start_shift'),
    path('end-shift/', end_shift, name='end_shift'),
    path('shift-history/',shift_history_view, name='shift_history'),
    path('admin-dashboard/lager/', lager_view, name='admin_lager'),
    path('admin-dashboard/lager/refill/<int:pk>/',refill_lager, name='refill_lager'),
    path('admin-dashboard/lager/update-target/<int:pk>/', update_target, name='update_target'),
    path('dashboard/worker/lager-refill/', LagerRefillView.as_view(), name='lager_refill_page'),
    path('.well-known/assetlinks.json', asset_links),

]

