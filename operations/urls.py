from django.urls import path
from .views import  SignupAPIView, LoginView, MenuListView, CreateOrderView, OrderDetailView, OrderListView

urlpatterns = [
    path('signup/', SignupAPIView.as_view(), name='signup_combined'),
    path('login/', LoginView.as_view(), name='login'),
    path('menu/', MenuListView.as_view(),name='menu'),
    path('orders/', CreateOrderView.as_view(), name='create-order'),
    path('orders/<int:order_id>/', OrderDetailView.as_view(), name='order-detail'),
    path('orders/list/', OrderListView.as_view(), name='order-list'),
]

