from django.urls import reverse_lazy
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken
from .forms import MenuItemForm
from .models import CustomUser, MenuItem, Order, OrderItem,Shift, ShiftReport, Lager
from .serializers import MenuItemSerializer, SignupSerializer, OrderSerializer
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth import authenticate, login,logout
from django.contrib.auth.hashers import make_password
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.db.models import Sum, Count
from django.views.generic import TemplateView, CreateView, UpdateView
from django.contrib.auth.decorators import login_required
from .utils import auto_complete_order_if_no_pending
from django.http import HttpResponseForbidden
from django.http import JsonResponse
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.decorators.http import require_POST
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction




class HomeView(View):
    def get(self, request):
        return render(request, 'home.html')


# 🔵 1. HTML form bilan ishlaydigan view
# operations/views.py (davomi)
class SignupHTMLView(View):
    def get(self, request):
        admin_count = CustomUser.objects.filter(role='admin').count()
        return render(request, 'signup.html', {
            'admin_limit_reached': admin_count >= 4
        })

    def post(self, request):
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        email = request.POST.get('email', '').strip()
        role = request.POST.get('role', 'customer')

        admin_count = CustomUser.objects.filter(role='admin').count()
        admin_limit_reached = admin_count >= 4

        # 🔒 Admin sonini cheklash
        if role == 'admin' and admin_limit_reached:
            return render(request, 'signup.html', {
                'error': '❌ Faqat 4 ta admin roli bo‘lishi mumkin.',
                'admin_limit_reached': True
            })

        # ❗ Bo‘sh maydonlarni tekshiramiz
        if not all([username, password, first_name, last_name, email]):
            return render(request, 'signup.html', {
                'error': 'Barcha maydonlarni to‘ldiring',
                'admin_limit_reached': admin_limit_reached
            })

        # ❌ Username mavjudligini tekshiramiz
        if CustomUser.objects.filter(username=username).exists():
            return render(request, 'signup.html', {
                'error': f"Username '{username}' allaqachon mavjud.",
                'admin_limit_reached': admin_limit_reached
            })

        # ❌ Email mavjudligini tekshiramiz
        if CustomUser.objects.filter(email=email).exists():
            return render(request, 'signup.html', {
                'error': f"E-mail '{email}' allaqachon ishlatilgan.",
                'admin_limit_reached': admin_limit_reached
            })
        is_approved = True if role == 'admin' else False

        # ✅ Foydalanuvchini yaratamiz
        CustomUser.objects.create(
            username=username,
            password=make_password(password),
            first_name=first_name,
            last_name=last_name,
            email=email,
            role=role,
            is_approved=is_approved
        )

        return redirect('/login/')


# 🔴 2. API uchun JSON POST view
@method_decorator(csrf_exempt, name='dispatch')  # API uchun CSRF ni o‘chiradi
class SignupAPIView(APIView):
    def post(self, request):
        serializer = SignupSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({'message': 'Foydalanuvchi yaratildi'}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LoginHTMLView(View):
    def get(self, request):
        return render(request, 'login.html')

    def post(self, request):
        username = request.POST.get('username')
        password = request.POST.get('password')

        # Avval username mavjudligini tekshiramiz
        if not CustomUser.objects.filter(username=username).exists():
            return render(request, 'login.html', {'error': 'Bunday username mavjud emas'})

        # Username mavjud, parolni tekshiramiz
        user = authenticate(request, username=username, password=password)
        if user is None:
            return render(request, 'login.html', {'error': 'Parol noto‘g‘ri'})

        # ✅ Admin tasdiqlaganini tekshiramiz
        if not user.is_approved:
            return render(request, 'login.html', {
                'error': 'Profilingiz hali admin tomonidan tasdiqlanmagan.'
            })

        # Tizimga kiritish
        login(request, user)

        # Role asosida yo‘naltirish
        if user.role == 'admin':
            return redirect('admin_dashboard')
        elif user.role == 'worker':
            return redirect('worker_dashboard')
        elif user.role == 'customer':
            return redirect('customer_orders')
        else:
            return redirect('home')



@login_required
def approve_user(request, user_id):
    if request.user.role != 'admin':
        return HttpResponseForbidden("Faqat admin foydalanuvchi tasdiqlashi mumkin.")

    user_to_approve = get_object_or_404(CustomUser, id=user_id)
    user_to_approve.is_approved = True
    user_to_approve.save()

    return redirect('admin_users')  # foydalanuvchilar ro‘yxati sahifasiga qaytarish

def reject_user(request, user_id):
    user = get_object_or_404(CustomUser, id=user_id)
    username = user.username  # debugging uchun
    user.delete()
    print(f"{username} foydalanuvchisi o‘chirildi")
    return redirect('admin_users')  # bu sahifa mavjud bo‘lishi kerak

def logout_view(request):
    logout(request)
    return redirect('home')  # yoki 'login_html'


class LoginView(APIView):
    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')

        user = authenticate(username=username, password=password)

        if user is not None:
            refresh = RefreshToken.for_user(user)
            return Response({
                'refresh': str(refresh),
                'access': str(refresh.access_token),
                'username': user.username,
                'role': user.role,
            }, status=status.HTTP_200_OK)

        return Response({'error': 'Invalid username or password'}, status=status.HTTP_401_UNAUTHORIZED)


@method_decorator(login_required, name='dispatch')
class EditProfileView(View):
    def get(self, request):
        return render(request, 'edit_profile.html', {'user': request.user})

    def post(self, request):
        user = request.user
        user.first_name = request.POST.get('first_name') or user.first_name
        user.last_name = request.POST.get('last_name') or user.last_name
        user.email = request.POST.get('email') or user.email

        password = request.POST.get('password')
        if password:
            user.set_password(password)  # faqat parol bo‘lsa yangilanadi

        user.save()
        return redirect('edit_profile')



class RoleRequiredMixin(LoginRequiredMixin):
    allowed_roles = []

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login_html')
        if request.user.role not in self.allowed_roles:
            return redirect('home')
        return super().dispatch(request, *args, **kwargs)


class MenuListView(APIView):
    def get(self, request):
        menu_items = MenuItem.objects.filter(available=True)
        serializer = MenuItemSerializer(menu_items, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = MenuItemSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class CreateOrderView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = OrderSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class OrderDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, order_id):
        try:
            order = Order.objects.get(id=order_id, customer=request.user)
        except Order.DoesNotExist:
            return Response({'error': 'Order not found'}, status=status.HTTP_404_NOT_FOUND)

        serializer = OrderSerializer(order)
        return Response(serializer.data)


class OrderListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        orders = Order.objects.filter(customer=request.user)
        serializer = OrderSerializer(orders, many=True)
        return Response(serializer.data)


class ProductOrderStatsView(APIView):
    def get(self, request):
        stats = (
            OrderItem.objects.values('menu_item__name')
            .annotate(
                total_quantity=Sum('quantity'),
                order_count=Count('order', distinct=True)
            )
            .order_by('-total_quantity')
        )
        return Response(stats)


class AdminDashboardView(RoleRequiredMixin, TemplateView):
    template_name = 'admin_dashboard.html'
    allowed_roles = ['admin']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Barcha mahsulotlarni ombor holati bilan birga yuboramiz
        context['menu_items'] = MenuItem.objects.all().order_by('name')
        return context

class AdminOrderListView(LoginRequiredMixin, View):
    def get(self, request):
        if request.user.role != 'admin':
            return redirect('home')

        orders = Order.objects.all().order_by('-created_at')
        return render(request, 'admin_orders.html', {'orders': orders})




@method_decorator(login_required, name='dispatch')
class AllUsersView(View):
    def get(self, request):
        if request.user.role != 'admin':
            return render(request, 'unauthorized.html')

        # 1. SARIQ BLOK: Tasdiqlanmagan hamma yangi foydalanuvchilar
        # is_approved=False bo'lgan har qanday foydalanuvchi shu yerga tushadi
        pending_users = CustomUser.objects.filter(
            is_approved=False
        ).exclude(role='admin').order_by('-date_joined')

        # 2. YASHIL BLOK: Tasdiqlangan aktiv xodimlar (Ishchi va Buro)
        active_staff = CustomUser.objects.filter(
            is_approved=True,
            is_active=True,
            role__in=['worker', 'buro']
        ).exclude(id=request.user.id)

        # 3. KULRANG BLOK: Tasdiqlangan aktiv mijozlar
        # Faqat is_approved=True bo'lgan mijozlar bu yerga o'tadi
        customers = CustomUser.objects.filter(
            is_approved=True,
            is_active=True,
            role='customer'
        )

        # 4. QORA BLOK: Ishdan bo'shatilganlar
        inactive_staff = CustomUser.objects.filter(
            is_approved=True,
            is_active=False
        ).exclude(role='admin')

        context = {
            'pending_users': pending_users,
            'active_staff': active_staff,
            'customers': customers,
            'inactive_staff': inactive_staff,
        }
        return render(request, 'admin_users.html', context)

# Tasdiqlash: is_approved ni True qiladi
def activate_worker(request, user_id):
    if request.user.role == 'admin':
        user = get_object_or_404(CustomUser, id=user_id)
        user.is_approved = True
        user.is_active = True # Tasdiqlanganda avtomatik aktiv bo'ladi
        user.save()
    return redirect('admin_users')

# Bo'shatish: is_active ni False qiladi, lekin is_approved True qoladi (Qora blokka tushishi uchun)
def deactivate_worker(request, user_id):
    if request.user.role == 'admin':
        user = get_object_or_404(CustomUser, id=user_id)
        user.is_active = False
        user.save()
    return redirect('admin_users')

class MenuCreateView(RoleRequiredMixin, CreateView):
    model = MenuItem
    form_class = MenuItemForm
    template_name = 'menu_create.html'
    success_url = reverse_lazy('admin_dashboard')
    allowed_roles = ['admin']


class MenuUpdateView(LoginRequiredMixin, UpdateView):
    model = MenuItem
    template_name = 'menu_update.html'
    fields = ['name', 'produkt_type', 'beschreibung', 'verfügbar']
    success_url = reverse_lazy('admin_dashboard')

    def dispatch(self, request, *args, **kwargs):
        if request.user.role != 'admin':
            return redirect('home')
        return super().dispatch(request, *args, **kwargs)


@login_required
@require_POST  # Faqat POST so'rov bilan o'chiriladi (xavfsizlik uchun)
def delete_menu_item(request, pk):
    if request.user.role != 'admin':
        return redirect('home')

    menu_item = get_object_or_404(MenuItem, pk=pk)

    # O'chirish
    menu_item.delete()

    messages.success(request, f"✅ {menu_item.name} muvaffaqiyatli o'chirildi.")
    return redirect('admin_dashboard')


class WorkerDashboardView(RoleRequiredMixin, TemplateView):
    template_name = 'worker_dashboard.html'
    allowed_roles = ['worker', 'admin', 'buro']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # 1. Aktiv smenani olamiz
        active_shift = Shift.objects.filter(worker=self.request.user, is_active=True).last()
        context['active_shift'] = active_shift

        # 2. Barcha mahsulotlar (Ombor holati bilan)
        products = MenuItem.objects.filter(verfügbar=True).select_related('stock').order_by('name')

        data = []
        for item in products:
            produced_sum = 0

            if active_shift:
                # ---------------------------------------------------------
                # ✅ TO'G'IRLANGAN QISM:
                # Endi biz NOMI va TURI bo'yicha aniq filtrlaymiz.
                # Shunda "Ganze 1/1 (Roh)" va "Ganze 1/1 (Gar)" alohida hisoblanadi.
                # ---------------------------------------------------------
                produced_sum = ShiftReport.objects.filter(
                    shift=active_shift,
                    product_name=item.name,  # Masalan: "Ganze 1/1"
                    product_type=item.produkt_type  # Masalan: "Roh" yoki "Gar"
                ).aggregate(total=Sum('quantity'))['total'] or 0

            # Ombordagi holat
            stock_kg = 0
            if hasattr(item, 'stock'):
                stock_kg = item.stock.current_stock

            data.append({
                'id': item.id,
                'name': item.name,
                'produkt_type': item.produkt_type,
                'pkg_size': 5 if item.produkt_type == 'Roh' else 4,
                'produziert_kg': produced_sum,
                'lager_kg': stock_kg
            })

        context['product_data'] = data
        return context


@login_required
@transaction.atomic
def worker_produce(request):
    if request.method == 'POST':
        active_shift = Shift.objects.filter(worker=request.user, is_active=True).last()
        if not active_shift:
            messages.error(request, "⚠️ Bitte Schicht starten!")
            return redirect('worker_dashboard')

        item_id = request.POST.get('menu_item_id')
        try:
            quantity = float(request.POST.get('quantity', 0))
        except (ValueError, TypeError):
            return redirect('worker_dashboard')

        if quantity <= 0:
            return redirect('worker_dashboard')

        menu_item = get_object_or_404(MenuItem, id=item_id)

        # 1. Tarixga yozish
        ShiftReport.objects.create(
            shift=active_shift,
            product_name=menu_item.name,
            product_type=menu_item.produkt_type,
            quantity=quantity
        )
        active_shift.total_packages_done += quantity
        active_shift.save()

        # 2. Qisman yopish mantig'i
        pending_items = OrderItem.objects.filter(
            menu_item=menu_item,
            status='pending'
        ).order_by('order__created_at')

        remaining_produced = quantity

        for item in pending_items:
            if remaining_produced <= 0:
                break

            if remaining_produced >= item.quantity:
                # Zakaz to'liq yopiladi
                remaining_produced -= item.quantity
                item.status = 'completed'
                item.save()
                auto_complete_order_if_no_pending(item.order)
            else:
                # ZAKAZNI BO'LISH (Qisman yopish)
                # 1. Yangi completed qator yaratamiz
                OrderItem.objects.create(
                    order=item.order,
                    menu_item=menu_item,
                    quantity=remaining_produced,
                    status='completed'
                )
                # 2. Eskisini kamaytiramiz (u pending bo'lib qolaveradi)
                item.quantity -= remaining_produced
                item.save()

                remaining_produced = 0
                break  # Hamma narsa tarqatildi

        # 3. Ortib qolgani omborga
        if remaining_produced > 0:
            lager, created = Lager.objects.get_or_create(menu_item=menu_item)
            lager.current_stock += remaining_produced
            lager.save()


    return redirect('worker_dashboard')


@csrf_exempt
@login_required
def cancel_order_item(request, item_id):
    item = get_object_or_404(OrderItem, id=item_id)
    order = item.order

    if item.status != 'cancelled':
        item.status = 'cancelled'
        item.save()

        remaining_items = order.orderitem_set.exclude(status='cancelled').exists()

        if not remaining_items:
            order.delete()
            return redirect('customer_orders')
        else:
            # Qolgan mahsulotlar bo'lsa, buyurtma statusini avtomatik yangilaymiz
            auto_complete_order_if_no_pending(order)

    return redirect('customer_orders')



class CustomerDashboardView(RoleRequiredMixin, TemplateView):
    template_name = 'customer_dashboard.html'
    allowed_roles = ['customer', 'admin', 'buro']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['menu_items'] = MenuItem.objects.filter(verfügbar=True)

        # 'orderitem' orqali bog'langan ma'lumotlarni oldindan yuklaymiz (Optimization)
        base_orders = Order.objects.filter(orderitem__isnull=False).distinct().prefetch_related('orderitem_set', 'orderitem_set__menu_item')

        if self.request.user.role in ['admin', 'buro']:
            context['orders'] = base_orders.order_by('-created_at')
        else:
            context['orders'] = base_orders.filter(user=self.request.user).order_by('-created_at')

        return context

class CreateOrderHTMLView(LoginRequiredMixin, View):
    def post(self, request):
        # Faqat order yaratamiz (bo‘sh holda)
        order = Order.objects.create(user=request.user)

        # OrderItemlar qo‘shish uchun sahifaga yo‘naltiramiz
        return redirect('add_items_to_order', order_id=order.id)


class AddItemsToOrderView(LoginRequiredMixin, View):
    # GET: Miqdor kiritish sahifasini ochish
    def get(self, request, order_id):
        order = get_object_or_404(Order, id=order_id, user=request.user)
        menu_items = MenuItem.objects.filter(verfügbar=True)
        return render(request, 'add_items.html', {
            'order': order,
            'menu_items': menu_items
        })

    # POST: Miqdorlarni saqlash va hisoblash
    def post(self, request, order_id):
        order = get_object_or_404(Order, id=order_id, user=request.user)
        item_ids = request.POST.getlist('items')

        if not item_ids:
            order.delete()
            messages.error(request, "Bitte wählen Sie mindestens ein Produkt aus.")
            return redirect('customer_dashboard')

        with transaction.atomic():
            has_items = False
            for item_id in item_ids:
                try:
                    menu_item = MenuItem.objects.get(id=item_id)
                    quantity_str = request.POST.get(f'quantity_{item_id}', '0')
                    quantity = int(float(quantity_str)) if quantity_str else 0

                    if quantity <= 0:
                        continue

                    lager, _ = Lager.objects.get_or_create(menu_item=menu_item)

                    if lager.current_stock >= quantity:
                        # Omborda yetarli
                        lager.current_stock -= quantity
                        lager.save()
                        OrderItem.objects.create(
                            order=order, menu_item=menu_item,
                            quantity=quantity, status='completed'
                        )
                    elif lager.current_stock > 0:
                        # Omborda bir qismi bor
                        stock_qty = lager.current_stock
                        production_qty = quantity - stock_qty
                        lager.current_stock = 0
                        lager.save()

                        OrderItem.objects.create(
                            order=order, menu_item=menu_item,
                            quantity=stock_qty, status='completed'
                        )
                        OrderItem.objects.create(
                            order=order, menu_item=menu_item,
                            quantity=production_qty, status='pending'
                        )
                    else:
                        # Omborda yo'q
                        OrderItem.objects.create(
                            order=order, menu_item=menu_item,
                            quantity=quantity, status='pending'
                        )
                    has_items = True
                except (MenuItem.DoesNotExist, ValueError):
                    continue

            # Buyurtma holatini yangilash
            if has_items:
                # 'orderitem_set' orqali xatolikni oldini olamiz
                if not order.orderitem_set.filter(status='pending').exists():
                    order.status = 'completed'
                else:
                    order.status = 'pending'
                order.save()
                messages.success(request, "Bestellung erfolgreich verarbeitet!")

                # MANA BU YER: Muvaffaqiyatli zakazdan keyin 'Orders' sahifasiga qaytadi
                return redirect('customer_orders')
            else:
                order.delete()
                return redirect('customer_dashboard')

class CustomerOrdersView(LoginRequiredMixin, View):
    def get(self, request):
        orders = Order.objects.filter(user=request.user).order_by('-created_at')

        # ❗ Bo‘sh va hali "pending" bo‘lgan orderlarni avtomatik "cancelled" qilamiz
        for order in orders:
            if order.status == 'pending' and not order.orderitem_set.exists():
                order.status = 'cancelled'
                order.save()

        return render(request, 'customer_orders.html', {'orders': orders})




def start_shift(request):
    if request.method == 'POST':
        # Yangi smena ochish
        Shift.objects.create(worker=request.user)
    return redirect('worker_dashboard')

def end_shift(request):
    if request.method == 'POST':
        shift = Shift.objects.filter(worker=request.user, is_active=True).last()
        if shift:
            # Hisob-kitob qilish shart emas, worker_produce buni qilib bo'lgan.
            # Faqat vaqtni belgilab yopamiz.
            shift.end_time = timezone.now()
            shift.is_active = False
            shift.save()

    return redirect('worker_dashboard')




def shift_history_view(request):
    # Tugatilgan smenalarni olamiz
    shifts_query = Shift.objects.filter(
        worker=request.user,
        is_active=False
    ).order_by('-end_time')

    shifts_data = []

    for shift in shifts_query:
        # YANGI: ShiftReport modelidan ma'lumot olamiz
        # 'reports' bu related_name (models.py da ShiftReport da yozilgan bo'lishi kerak)
        # Agar related_name yozilmagan bo'lsa: ShiftReport.objects.filter(shift=shift)...

        summary = ShiftReport.objects.filter(shift=shift).values('product_name').annotate(
            total_kg=Sum('quantity')
        ).order_by('product_name')

        shifts_data.append({
            'shift': shift,
            'summary': summary
        })

    return render(request, 'shift_history.html', {'shifts_data': shifts_data})

@login_required
def lager_view(request):
    if request.user.role != 'admin':
        return redirect('home')

    # MenuItem orqali bog'langan stock (Lager) ma'lumotlarini olamiz
    # Bu usul jadvalda barcha mahsulotlar ko'rinishini ta'minlaydi
    items = MenuItem.objects.all().order_by('name')
    return render(request, 'admin_lager.html', {'items': items})




def asset_links(request):
    data = [{
        "relation": ["delegate_permission/common.handle_all_urls"],
        "target": {
            "namespace": "android_app",
            "package_name": "de.kartoffelfirma.app", # NEMISCHA NOMI
            "sha256_cert_fingerprints": ["AC:58:76:ED:53:00:16:5B:BC:36:FE:F6:AE:3E:B1:99:98:02:DA:8B:E0:9B:1A:0D:D1:E4:E7:55:08:B2:61:29"]
        }
    }]
    return JsonResponse(data, safe=False)