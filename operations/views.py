from django.db import transaction
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
from django.contrib.auth.decorators import login_required, user_passes_test
from .utils import auto_complete_order_if_no_pending
from django.http import HttpResponseForbidden
from django.http import JsonResponse
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin



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
        messages.success(request, '✅ Profil ma’lumotlari yangilandi.')
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


# views.py
class LagerRefillView(RoleRequiredMixin, TemplateView):
    template_name = 'lager_refill.html'
    allowed_roles = ['worker', 'admin']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from django.db.models import F

        # 'shortage_kg' nomini annotatsiyada ishlatamiz
        refill_items = Lager.objects.select_related('menu_item').annotate(
            shortage_kg=F('target_amount') - F('current_stock')
        ).order_by('-shortage_kg')

        context['refill_data'] = refill_items
        # Smena holatini tekshirish
        context['active_shift'] = Shift.objects.filter(worker=self.request.user, is_active=True).last()
        return context


@login_required
@transaction.atomic
def refill_lager(request, pk):
    active_shift = Shift.objects.filter(worker=request.user, is_active=True).last()

    if not active_shift:
        messages.error(request, "⚠️ Iltimos, avval smenani boshlang!")
        return redirect('lager_refill_page')

    if request.method == 'POST':
        lager = get_object_or_404(Lager, menu_item_id=pk)
        try:
            input_amount = float(request.POST.get('num_packages', 0))
            p_type = lager.menu_item.produkt_type  # Mahsulot turi (Roh yoki Gar)

            # 1. KARRALILIK TEKSHIRUVI (Modelga tegmasdan)
            if p_type == 'Roh' and input_amount % 5 != 0:
                messages.error(request, f"🛑 {lager.menu_item.name} (Roh) faqat 5 kg lik qadoqlarda bo'lishi shart!")
                return redirect('lager_refill_page')

            if p_type == 'Gar' and input_amount % 4 != 0:
                messages.error(request, f"🛑 {lager.menu_item.name} (Gar) faqat 4 kg lik qadoqlarda bo'lishi shart!")
                return redirect('lager_refill_page')

            # 2. REJA LIMITI TEKSHIRUVI
            max_allowed = lager.target_amount - lager.current_stock
            if max_allowed <= 0:
                messages.error(request, "🛑 Reja allaqachon to'lgan!")
                return redirect('lager_refill_page')

            if input_amount > max_allowed:
                messages.error(request, f"🛑 Limitdan oshdi! Maksimal {max_allowed} kg qo'sha olasiz.")
                return redirect('lager_refill_page')

            # 3. SAQLASH
            if input_amount > 0:
                lager.current_stock += input_amount
                lager.save()

                OrderItem.objects.create(
                    order=None,
                    menu_item=lager.menu_item,
                    quantity=input_amount,
                    status='completed',
                    shift=active_shift
                )
                messages.success(request, f"✅ {lager.menu_item.name} omborga qo'shildi.")
        except ValueError:
            messages.error(request, "⚠️ Miqdor xato kiritildi.")

    return redirect('lager_refill_page')


from django.db.models import Sum, Q

class WorkerDashboardView(RoleRequiredMixin, TemplateView):
    template_name = 'worker_dashboard.html'
    allowed_roles = ['worker', 'admin', 'buro'] # Admin/Buro ham ko'ra olishi uchun

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        active_shift = Shift.objects.filter(worker=self.request.user, is_active=True).last()
        context['active_shift'] = active_shift

        # 1. Barcha kerakli ma'lumotlarni bitta so'rovda yig'amiz
        # Smenadagi natijalarni faqat smena bo'lsagina hisoblaymiz
        shift_filter = Q(orderitem__shift=active_shift, orderitem__status='completed') if active_shift else Q(pk__in=[])

        products_query = MenuItem.objects.filter(
            orderitem__status='pending'
        ).annotate(
            total_wartend=Sum('orderitem__quantity', filter=Q(orderitem__status='pending')),
            completed_session_kg=Sum('orderitem__quantity', filter=shift_filter)
        ).select_related('stock').distinct().order_by('-total_wartend')

        all_products = []
        for item in products_query:
            all_products.append({
                'id': item.id,
                'name': item.name,
                'produkt_type': item.produkt_type,
                # Roh bo'lsa 5, aks holda 4 kg qadoq
                'pkg_size': 5 if item.produkt_type == 'Roh' else 4,
                'order_pending': item.total_wartend or 0,
                'completed_session_kg': item.completed_session_kg or 0,
                'current_stock': item.stock.current_stock if hasattr(item, 'stock') else 0,
            })

        context['product_data'] = all_products
        return context


@login_required
@transaction.atomic
def complete_product_view(request, menu_item_id):
    active_shift = Shift.objects.filter(worker=request.user, is_active=True).last()

    # 1. Smena nazorati
    if not active_shift:
        messages.error(request, "⚠️ Bitte starten Sie zuerst eine Schicht!")
        return redirect('worker_dashboard')

    if request.method == 'POST':
        # 2. Miqdorni olish
        num_packages = request.POST.get('num_packages')
        try:
            kg_produced = int(float(num_packages)) if num_packages else 0
        except (ValueError, TypeError):
            kg_produced = 0

        if kg_produced <= 0:
            return redirect('worker_dashboard')

        menu_item = get_object_or_404(MenuItem, id=menu_item_id)

        # 3. Faqat pending (kutilayotgan) zakazlarni yopish mantiqi (FIFO)
        pending_items = OrderItem.objects.filter(
            menu_item=menu_item,
            status='pending'
        ).order_by('order__created_at')

        remaining_kg = kg_produced

        for item in pending_items:
            if remaining_kg <= 0:
                break

            if remaining_kg >= item.quantity:
                # Zakaz to'liq yopiladi
                remaining_kg -= item.quantity
                item.status = 'completed'
                item.shift = active_shift
                item.save()

                # Buyurtma statusini tekshiramiz
                auto_complete_order_if_no_pending(item.order)
            else:
                # Zakaz qisman yopiladi: bajarilgan qismi uchun yangi qator
                OrderItem.objects.create(
                    order=item.order,
                    menu_item=menu_item,
                    quantity=remaining_kg,
                    status='completed',
                    shift=active_shift
                )
                # Qolgan qismi pending bo'lib turaveradi
                item.quantity -= remaining_kg
                item.save()

                # Bu yerda status hali pendingligicha qoladi,
                # chunki item.quantity hali bor.
                remaining_kg = 0

        messages.success(request, f"✅ {kg_produced} kg mahsulot zakazlar uchun qayd etildi.")

    return redirect('worker_dashboard')


@csrf_exempt
@login_required
def cancel_order_item(request, item_id):
    item = get_object_or_404(OrderItem, id=item_id)
    order = item.order

    if item.status != 'cancelled':
        item.status = 'cancelled'
        item.save()

        # Buyurtmada bekor qilinmagan mahsulotlar borligini tekshiramiz
        remaining_items = order.orderitem_set.exclude(status='cancelled').exists()

        if not remaining_items:
            # Agar barcha mahsulotlar bekor qilingan bo'lsa, buyurtmani o'chiramiz
            order.delete()
            messages.info(request, "Die leere Bestellung wurde gelöscht.")
            # MANA BU YER: 'worker_dashboard' o'rniga 'customer_orders'
            return redirect('customer_orders')
        else:
            # Qolgan mahsulotlar bo'lsa, buyurtma statusini avtomatik yangilaymiz
            auto_complete_order_if_no_pending(order)

    messages.success(request, f"{item.menu_item.name} wurde storniert.")
    # Har qanday holatda ham buyurtmalar sahifasida qolamiz
    return redirect('customer_orders')

@csrf_exempt
@login_required
def reset_all_completed(request):
    if request.method == 'POST':
        keys_to_delete = [key for key in request.session.keys() if key.startswith("completed_")]
        for key in keys_to_delete:
            del request.session[key]
    return redirect('worker_dashboard')


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
                messages.error(request, "Keine gültigen Mengen eingegeben.")
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
        messages.success(request, "Schicht gestartet! Viel Erfolg.")
    return redirect('worker_dashboard')

def end_shift(request):
    if request.method == 'POST':
        shift = Shift.objects.filter(worker=request.user, is_active=True).last()
        if shift:
            total_done_kg = 0

            # 1. Shu smenada yopilgan barcha mahsulot turlarini aniqlaymiz
            # OrderItem dagi shift maydoni orqali bazadan filtrlaymiz
            produced_items = OrderItem.objects.filter(shift=shift, status='completed')

            # Mahsulotlar bo'yicha guruhlab hisoblaymiz
            distinct_products = produced_items.values('menu_item__name').annotate(total_kg=Sum('quantity'))

            for entry in distinct_products:
                name = entry['menu_item__name']
                kg = entry['total_kg']

                # TARIXGA YOZISH (Database orqali)
                ShiftReport.objects.create(
                    shift=shift,
                    product_name=name,
                    quantity=kg  # Endi jami kg yoziladi
                )
                total_done_kg += kg

            # 2. Smenani yopamiz
            shift.end_time = timezone.now()
            shift.total_packages_done = total_done_kg  # Bu yerda kg saqlanadi
            shift.is_active = False
            shift.save()

            # Sessionni tozalash (ehtiyot shart, agar eski qoldiqlari bo'lsa)
            for key in list(request.session.keys()):
                if key.startswith('completed_pkgs_'):
                    del request.session[key]

            messages.success(request, f"Schicht beendet. Gesamt: {total_done_kg} kg produziert.")

    return redirect('worker_dashboard')



from django.db.models import Sum

def shift_history_view(request):
    # Tugatilgan smenalarni olamiz
    shifts_query = Shift.objects.filter(
        worker=request.user,
        is_active=False
    ).order_by('-end_time')

    shifts_data = []

    for shift in shifts_query:
        # 'order' maydonini guruhlashga qo'shamiz (order=None bo'lsa Ombor, aks holda Zakaz)
        summary = shift.produced_items.filter(status='completed').values(
            'menu_item__name',
            'menu_item__produkt_type',
            'order'  # <-- BU MUHIM: Zakaz yoki Omborni ajratish uchun
        ).annotate(
            total_kg=Sum('quantity')
        ).order_by('menu_item__name', 'order')

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


@login_required
@user_passes_test(lambda u: u.is_staff)
def update_target(request, pk):
    if request.method == 'POST':
        menu_item = get_object_or_404(MenuItem, pk=pk)
        lager, created = Lager.objects.get_or_create(menu_item=menu_item)

        new_target_raw = request.POST.get('target_amount')
        if new_target_raw:
            try:
                new_target = float(new_target_raw)
                current_stock = lager.current_stock
                p_type = menu_item.produkt_type

                # 1. Qoldiqdan kamaytirmaslik tekshiruvi
                if new_target < current_stock:
                    messages.error(request,
                                   f"🛑 Xato! Yangi reja hozirgi qoldiqdan ({current_stock:.0f} kg) kam bo'lishi mumkin emas.")
                    return redirect('admin_lager')

                # 2. Karralilik tekshiruvi
                if p_type == 'Roh' and new_target % 5 != 0:
                    messages.error(request, f"🛑 {menu_item.name} uchun reja 5 ga karrali bo'lishi shart.")
                    return redirect('admin_lager')

                if p_type == 'Gar' and new_target % 4 != 0:
                    messages.error(request, f"🛑 {menu_item.name} uchun reja 4 ga karrali bo'lishi shart.")
                    return redirect('admin_lager')

                # Saqlash
                lager.target_amount = new_target
                lager.save()

                # ✅ To'g'ri Python formati: {new_target:.0f}
                messages.success(request, f"✅ {menu_item.name} Soll-Bestand wurde auf {new_target:.0f} kg aktualisiert.")

            except ValueError:
                messages.error(request, "⚠️ Raqam kiritishda xato.")

    return redirect('admin_lager')


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