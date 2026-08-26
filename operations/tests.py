import datetime
from unittest.mock import patch
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from operations.models import CustomUser, MenuItem, Order, OrderItem, FactorySettings
from operations.forms import FactorySettingsForm
from operations import capacity_planner
from operations.services import split_order_into_hourly_chunks, get_production_tasks, get_hourly_availability




class FactorySettingsModelTest(TestCase):
    def test_singleton_get_settings_creates_defaults(self):
        settings = FactorySettings.get_settings()
        self.assertIsNotNone(settings)
        self.assertEqual(settings.palettes_per_hour, 2.0)
        self.assertEqual(settings.kg_per_palette, 625.0)
        self.assertEqual(settings.hourly_production_target_kg, 1250.0)
        self.assertEqual(settings.daily_production_target_kg, 30000.0)
        self.assertEqual(settings.buro_working_start, datetime.time(8, 0))
        self.assertEqual(settings.buro_working_end, datetime.time(17, 0))
        self.assertEqual(settings.production_working_start, datetime.time(6, 0))
        self.assertEqual(settings.production_working_end, datetime.time(22, 0))
        self.assertEqual(settings.next_day_cutoff_time, datetime.time(22, 0))
        self.assertEqual(settings.cut_off_time, datetime.time(22, 0))

        settings.cut_off_time = datetime.time(21, 0)
        self.assertEqual(settings.next_day_cutoff_time, datetime.time(21, 0))
        self.assertEqual(settings.cut_off_time, datetime.time(21, 0))

    def test_singleton_always_uses_pk_1(self):
        settings1 = FactorySettings.get_settings()
        settings1.palettes_per_hour = 3.0
        settings1.kg_per_palette = 500.0
        settings1.save()

        settings2 = FactorySettings.objects.create(
            palettes_per_hour=4.0,
            kg_per_palette=500.0,
            buro_working_start=datetime.time(9, 0),
            buro_working_end=datetime.time(18, 0),
            production_working_start=datetime.time(7, 0),
            production_working_end=datetime.time(23, 0),
            next_day_cutoff_time=datetime.time(21, 30),
        )
        self.assertEqual(settings2.pk, 1)
        self.assertEqual(FactorySettings.objects.count(), 1)
        reloaded = FactorySettings.get_settings()
        self.assertEqual(reloaded.palettes_per_hour, 4.0)
        self.assertEqual(reloaded.kg_per_palette, 500.0)
        self.assertEqual(reloaded.hourly_production_target_kg, 2000.0)
        self.assertEqual(reloaded.daily_production_target_kg, 48000.0)


class CapacityPlannerTest(TestCase):
    def setUp(self):
        self.settings = FactorySettings.get_settings()
        self.settings.palettes_per_hour = 2.0
        self.settings.kg_per_palette = 625.0  # 2.0 * 625 = 1250 kg/h -> 30,000 kg / 24h
        self.settings.next_day_cutoff_time = datetime.time(22, 0)
        self.settings.save()

        self.user = CustomUser.objects.create_user(
            username='customer1',
            email='customer1@test.com',
            password='password123',
            role='customer',
            is_approved=True
        )
        self.menu_item = MenuItem.objects.create(
            name='Krone Roh 5kg',
            produkt_type='Roh',
            verfügbar=True
        )

    def test_hourly_and_daily_target_calculations(self):
        # Default 2.0 Pal/h * 625 kg = 1250 kg/h -> 30,000 kg per 24h
        hourly = capacity_planner.get_hourly_production_target_kg(self.settings)
        daily = capacity_planner.get_daily_production_target_kg(self.settings)
        pal_hr = capacity_planner.get_palettes_per_hour(self.settings)
        kg_pal = capacity_planner.get_kg_per_palette(self.settings)
        self.assertEqual(pal_hr, 2.0)
        self.assertEqual(kg_pal, 625.0)
        self.assertEqual(hourly, 1250.0)
        self.assertEqual(daily, 30000.0)

        # Dynamic setting update (e.g. 3.0 Pal/h * 500 kg = 1500 kg/h -> 36,000 kg / 24h)
        self.settings.palettes_per_hour = 3.0
        self.settings.kg_per_palette = 500.0
        self.settings.save()

        hourly_dyn = capacity_planner.get_hourly_production_target_kg(self.settings)
        daily_dyn = capacity_planner.get_daily_production_target_kg(self.settings)
        self.assertEqual(hourly_dyn, 1500.0)
        self.assertEqual(daily_dyn, 36000.0)

    def test_determine_target_production_date_cutoff(self):
        test_date = datetime.date(2026, 8, 20)

        # 14:00 (before 22:00 cutoff) -> same day
        before_cutoff = datetime.datetime.combine(test_date, datetime.time(14, 0))
        target_before = capacity_planner.determine_target_production_date(before_cutoff, self.settings)
        self.assertEqual(target_before, test_date)

        # 22:30 (after 22:00 cutoff) -> next day
        after_cutoff = datetime.datetime.combine(test_date, datetime.time(22, 30))
        target_after = capacity_planner.determine_target_production_date(after_cutoff, self.settings)
        self.assertEqual(target_after, test_date + datetime.timedelta(days=1))

        # Dynamic cutoff change to 18:00
        self.settings.next_day_cutoff_time = datetime.time(18, 0)
        self.settings.save()

        at_19_00 = datetime.datetime.combine(test_date, datetime.time(19, 0))
        target_dynamic = capacity_planner.determine_target_production_date(at_19_00, self.settings)
        self.assertEqual(target_dynamic, test_date + datetime.timedelta(days=1))

    def test_order_capacity_checks(self):
        target_date = datetime.date(2026, 8, 25)

        # Target is 30,000 kg (2.0 * 625 * 24). Order of 15,000 kg should be feasible
        check1 = capacity_planner.check_order_capacity(15000.0, target_date=target_date, settings=self.settings)
        self.assertTrue(check1['is_feasible'])
        self.assertEqual(check1['palettes_per_hour'], 2.0)
        self.assertEqual(check1['kg_per_palette'], 625.0)
        self.assertEqual(check1['hourly_production_target_kg'], 1250.0)
        self.assertEqual(check1['daily_production_target_kg'], 30000.0)
        self.assertEqual(check1['remaining_capacity_kg'], 30000.0)
        self.assertEqual(check1['exceeded_by_kg'], 0.0)

        # Create actual orders for 20,000 kg on target date
        order = Order.objects.create(user=self.user, status='pending')
        order.created_at = timezone.make_aware(datetime.datetime.combine(target_date, datetime.time(10, 0)))
        order.save()

        OrderItem.objects.create(
            order=order,
            menu_item=self.menu_item,
            quantity=20000,
            status='pending'
        )

        # Remaining capacity on target_date is now 10,000 kg
        remaining = capacity_planner.get_remaining_daily_capacity_kg(target_date, self.settings)
        self.assertEqual(remaining, 10000.0)

        # Order of 5,000 kg fits
        check2 = capacity_planner.check_order_capacity(5000.0, target_date=target_date, settings=self.settings)
        self.assertTrue(check2['is_feasible'])
        self.assertEqual(check2['remaining_capacity_kg'], 10000.0)

        # Order of 15,000 kg exceeds remaining 10,000 kg by 5,000 kg
        check3 = capacity_planner.check_order_capacity(15000.0, target_date=target_date, settings=self.settings)
        self.assertFalse(check3['is_feasible'])
        self.assertEqual(check3['exceeded_by_kg'], 5000.0)
        self.assertEqual(check3['suggested_next_available_date'], target_date + datetime.timedelta(days=1))

    def test_working_hours_checks(self):
        # Buro: 08:00 - 17:00
        self.assertTrue(capacity_planner.is_within_buro_hours(datetime.time(10, 0), self.settings))
        self.assertFalse(capacity_planner.is_within_buro_hours(datetime.time(19, 0), self.settings))

        # Production: 06:00 - 22:00
        self.assertTrue(capacity_planner.is_within_production_hours(datetime.time(7, 30), self.settings))
        self.assertFalse(capacity_planner.is_within_production_hours(datetime.time(23, 15), self.settings))

    def test_capacity_summary(self):
        start_date = datetime.date(2026, 9, 1)
        summary = capacity_planner.get_capacity_summary(start_date=start_date, days=3, settings=self.settings)
        self.assertEqual(len(summary), 3)
        self.assertEqual(summary[0]['palettes_per_hour'], 2.0)
        self.assertEqual(summary[0]['kg_per_palette'], 625.0)
        self.assertEqual(summary[0]['hourly_target_kg'], 1250.0)
        self.assertEqual(summary[0]['daily_target_kg'], 30000.0)
        self.assertEqual(summary[0]['date'], start_date)


class FactorySettingsViewsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin = CustomUser.objects.create_user(
            username='admin_boss',
            email='admin@kartoffelfirma.de',
            password='secretpassword',
            role='admin',
            is_approved=True
        )
        self.worker = CustomUser.objects.create_user(
            username='worker_bob',
            email='worker@kartoffelfirma.de',
            password='secretpassword',
            role='worker',
            is_approved=True
        )

    def test_admin_settings_view_access(self):
        # Unauthenticated user redirected
        resp = self.client.get(reverse('admin_factory_settings'))
        self.assertEqual(resp.status_code, 302)

        # Worker role not allowed
        self.client.login(username='worker_bob', password='secretpassword')
        resp_worker = self.client.get(reverse('admin_factory_settings'))
        self.assertEqual(resp_worker.status_code, 302)

        # Admin allowed
        self.client.login(username='admin_boss', password='secretpassword')
        resp_admin = self.client.get(reverse('admin_factory_settings'))
        self.assertEqual(resp_admin.status_code, 200)
        self.assertContains(resp_admin, "Fabrikeinstellungen")
        self.assertContains(resp_admin, "2.0")
        self.assertContains(resp_admin, "625")

    def test_admin_settings_update_post(self):
        self.client.login(username='admin_boss', password='secretpassword')
        post_data = {
            'palettes_per_hour': '2.5',
            'kg_per_palette': '600.0',
            'buro_working_start': '08:30',
            'buro_working_end': '17:30',
            'production_working_start': '05:30',
            'production_working_end': '22:30',
            'next_day_cutoff_time': '21:00',
        }
        resp = self.client.post(reverse('admin_factory_settings'), data=post_data)
        self.assertEqual(resp.status_code, 302)

        updated_settings = FactorySettings.get_settings()
        self.assertEqual(updated_settings.palettes_per_hour, 2.5)
        self.assertEqual(updated_settings.kg_per_palette, 600.0)
        self.assertEqual(updated_settings.hourly_production_target_kg, 1500.0)
        self.assertEqual(updated_settings.daily_production_target_kg, 36000.0)
        self.assertEqual(updated_settings.next_day_cutoff_time, datetime.time(21, 0))

    def test_admin_dashboard_view_contains_factory_settings(self):
        self.client.login(username='admin_boss', password='secretpassword')
        resp = self.client.get(reverse('admin_dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('factory_settings', resp.context)
        self.assertEqual(resp.context['factory_settings'].hourly_production_target_kg, 1250.0)
        self.assertContains(resp, "Fabrik-Kapazität & Parameter")
        self.assertContains(resp, "1250 kg/h")
        self.assertContains(resp, "30000 kg")


class ProfileUpdateViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin = CustomUser.objects.create_user(
            username='admin_user',
            email='admin@test.de',
            password='password123',
            role='admin',
            first_name='Admin',
            last_name='Original',
            is_approved=True
        )
        self.customer = CustomUser.objects.create_user(
            username='customer_user',
            email='customer@test.de',
            password='password123',
            role='customer',
            first_name='Customer',
            last_name='Original',
            is_approved=True
        )
        self.worker = CustomUser.objects.create_user(
            username='worker_user',
            email='worker@test.de',
            password='password123',
            role='worker',
            first_name='Worker',
            last_name='Original',
            is_approved=True
        )

    def test_admin_profile_update_redirects_to_admin_dashboard(self):
        self.client.login(username='admin_user', password='password123')
        post_data = {
            'first_name': 'AdminUpdated',
            'last_name': 'Chief',
            'email': 'admin_updated@test.de',
        }
        resp = self.client.post(reverse('edit_profile'), data=post_data)
        self.assertRedirects(resp, reverse('admin_dashboard'))

        self.admin.refresh_from_db()
        self.assertEqual(self.admin.first_name, 'AdminUpdated')
        self.assertEqual(self.admin.last_name, 'Chief')
        self.assertEqual(self.admin.email, 'admin_updated@test.de')

    def test_customer_profile_update_redirects_to_customer_dashboard(self):
        self.client.login(username='customer_user', password='password123')
        post_data = {
            'first_name': 'CustomerUpdated',
            'last_name': 'Client',
            'email': 'customer_updated@test.de',
        }
        resp = self.client.post(reverse('edit_profile'), data=post_data)
        self.assertRedirects(resp, reverse('customer_dashboard'))

        self.customer.refresh_from_db()
        self.assertEqual(self.customer.first_name, 'CustomerUpdated')
        self.assertEqual(self.customer.last_name, 'Client')

    def test_worker_profile_update_redirects_to_worker_dashboard(self):
        self.client.login(username='worker_user', password='password123')
        post_data = {
            'first_name': 'WorkerUpdated',
            'last_name': 'Operator',
            'email': 'worker_updated@test.de',
        }
        resp = self.client.post(reverse('edit_profile'), data=post_data)
        self.assertRedirects(resp, reverse('worker_dashboard'))

        self.worker.refresh_from_db()
        self.assertEqual(self.worker.first_name, 'WorkerUpdated')


class BuroWorkingHoursMixinTest(TestCase):
    def setUp(self):

        self.client = Client()
        self.customer = CustomUser.objects.create_user(
            username='kurt_kunde',
            email='kurt@kunde.de',
            password='customerpass',
            role='customer',
            is_approved=True
        )
        self.settings = FactorySettings.get_settings()
        self.settings.palettes_per_hour = 2.0
        self.settings.kg_per_palette = 625.0
        self.settings.save()

        self.item_roh = MenuItem.objects.create(
            name='Agria Roh 5kg',
            produkt_type='Roh',
            verfügbar=True
        )

    def test_get_blocked_outside_working_hours(self):
        # Configure Büro working hours to a past 1-minute window
        self.settings.buro_working_start = datetime.time(0, 0)
        self.settings.buro_working_end = datetime.time(0, 1)
        self.settings.save()

        self.client.login(username='kurt_kunde', password='customerpass')
        order = Order.objects.create(user=self.customer)

        # GET on customer dashboard outside hours renders out_of_hours.html
        resp_dash = self.client.get(reverse('customer_dashboard'))
        self.assertEqual(resp_dash.status_code, 200)
        self.assertContains(resp_dash, "Das Büro ist derzeit geschlossen.")
        self.assertContains(resp_dash, "Unsere Büro-Öffnungszeiten:")

        # GET on add_items_to_order outside hours renders out_of_hours.html
        resp_items = self.client.get(reverse('add_items_to_order', args=[order.id]))
        self.assertEqual(resp_items.status_code, 200)
        self.assertContains(resp_items, "Das Büro ist derzeit geschlossen.")

        # GET on customer_orders outside hours renders out_of_hours.html
        resp_orders = self.client.get(reverse('customer_orders'))
        self.assertEqual(resp_orders.status_code, 200)
        self.assertContains(resp_orders, "Das Büro ist derzeit geschlossen.")

    def test_post_allowed_outside_working_hours(self):
        # Outside working hours
        self.settings.buro_working_start = datetime.time(0, 0)
        self.settings.buro_working_end = datetime.time(0, 1)
        self.settings.save()

        self.client.login(username='kurt_kunde', password='customerpass')
        order = Order.objects.create(user=self.customer)

        # POST submission (in-flight order completion) MUST be permitted!
        post_data = {
            'items': [str(self.item_roh.id)],
            f'quantity_{self.item_roh.id}': '250',
        }
        resp = self.client.post(reverse('add_items_to_order', args=[order.id]), data=post_data)
        # Should NOT be blocked with out_of_hours; should process and redirect
        self.assertEqual(resp.status_code, 302)

        order.refresh_from_db()
        self.assertEqual(order.orderitem_set.count(), 1)
        self.assertEqual(order.orderitem_set.first().quantity, 250)

    def test_get_allowed_inside_working_hours(self):
        # Configure Büro working hours to cover full 24h day
        self.settings.buro_working_start = datetime.time(0, 0)
        self.settings.buro_working_end = datetime.time(23, 59)
        self.settings.save()

        self.client.login(username='kurt_kunde', password='customerpass')
        order = Order.objects.create(user=self.customer)

        resp_dash = self.client.get(reverse('customer_dashboard'))
        self.assertEqual(resp_dash.status_code, 200)
        self.assertNotContains(resp_dash, "Das Büro ist derzeit geschlossen.")
        self.assertContains(resp_dash, "Bestellung erstellen")

        resp_items = self.client.get(reverse('add_items_to_order', args=[order.id]))
        self.assertEqual(resp_items.status_code, 200)
        self.assertNotContains(resp_items, "Das Büro ist derzeit geschlossen.")
        self.assertContains(resp_items, "Bestellung aufgeben")



class CustomerOrderCapacityFlowTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.customer = CustomUser.objects.create_user(
            username='kurt_kunde',
            email='kurt@kunde.de',
            password='customerpass',
            role='customer',
            is_approved=True
        )
        self.settings = FactorySettings.get_settings()
        self.settings.palettes_per_hour = 2.0
        self.settings.kg_per_palette = 625.0  # 1250 kg/h -> 30,000 kg / 24h
        self.settings.buro_working_start = datetime.time(0, 0)
        self.settings.buro_working_end = datetime.time(23, 59)
        self.settings.save()

        self.item_roh = MenuItem.objects.create(
            name='Agria Roh 5kg',
            produkt_type='Roh',
            verfügbar=True
        )
        self.item_gar = MenuItem.objects.create(
            name='Belana Gar 4kg',
            produkt_type='Gar',
            verfügbar=True
        )

    def test_add_items_get_displays_capacity_metrics(self):
        self.client.login(username='kurt_kunde', password='customerpass')
        order = Order.objects.create(user=self.customer)

        resp = self.client.get(reverse('add_items_to_order', args=[order.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('remaining_capacity_kg', resp.context)
        self.assertEqual(resp.context['remaining_capacity_kg'], 30000.0)
        self.assertIn('hourly_target_kg', resp.context)
        self.assertEqual(resp.context['hourly_target_kg'], 1250.0)
        self.assertContains(resp, "Verfügbare Kapazität (24h)")
        self.assertContains(resp, "1250 kg/h")

    def test_add_items_post_within_capacity_succeeds(self):
        self.client.login(username='kurt_kunde', password='customerpass')
        order = Order.objects.create(user=self.customer)

        post_data = {
            'items': [str(self.item_roh.id)],
            f'quantity_{self.item_roh.id}': '500',  # 500 kg
        }
        resp = self.client.post(reverse('add_items_to_order', args=[order.id]), data=post_data)
        self.assertEqual(resp.status_code, 302)  # Redirects to customer_orders on success
        self.assertRedirects(resp, reverse('customer_orders'))

        # Check order items created
        order.refresh_from_db()
        self.assertEqual(order.orderitem_set.count(), 1)
        self.assertEqual(order.orderitem_set.first().quantity, 500)

    def test_add_items_post_exceeding_capacity_is_blocked(self):
        self.client.login(username='kurt_kunde', password='customerpass')
        order = Order.objects.create(user=self.customer)

        # 24h capacity is 30,000 kg. Trying to order 35,000 kg exceeds capacity
        post_data = {
            'items': [str(self.item_roh.id)],
            f'quantity_{self.item_roh.id}': '35000',
        }
        resp = self.client.post(reverse('add_items_to_order', args=[order.id]), data=post_data)
        self.assertEqual(resp.status_code, 200)  # Re-renders page with error message

        # Verify order items were NOT created
        self.assertEqual(order.orderitem_set.count(), 0)

        # Verify error message contains capacity details
        self.assertContains(resp, "überschritten um 5000.0 kg")
        self.assertContains(resp, "Tageskapazität (24h): 30000 kg")


class ProductionSchedulerAndDashboardTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.worker = CustomUser.objects.create_user(
            username='worker_willy',
            email='willy@factory.de',
            password='workerpassword',
            role='worker',
            is_approved=True
        )
        self.customer = CustomUser.objects.create_user(
            username='karl_kunde',
            email='karl@kunde.de',
            password='customerpass',
            role='customer',
            is_approved=True
        )
        self.settings = FactorySettings.get_settings()
        self.settings.palettes_per_hour = 5.0
        self.settings.kg_per_palette = 625.0
        self.settings.save()

        self.item = MenuItem.objects.create(
            name='Gala Roh 5kg',
            produkt_type='Roh',
            verfügbar=True
        )

    def test_backward_scheduling_example_case(self):
        """
        Verify the exact business logic example:
        If an order requires 15 palettes and factory capacity is 5 palettes/hr,
        split it into 3 tasks of 5 palettes each.
        If pickup is at 18:00, chunks are scheduled for 17:00, 16:00, and 15:00.
        Chronological sorting has 15:00 at the top.
        """
        chunks = split_order_into_hourly_chunks(
            palettes_count=15.0,
            pickup_time=datetime.time(18, 0),
            palettes_per_hour=5.0,
            kg_per_palette=625.0
        )

        self.assertEqual(len(chunks), 3)

        # First chunk: 15:00 - 16:00 (5 palettes, 3125 kg)
        self.assertEqual(chunks[0]['start_time'], datetime.time(15, 0))
        self.assertEqual(chunks[0]['end_time'], datetime.time(16, 0))
        self.assertEqual(chunks[0]['palettes'], 5.0)
        self.assertEqual(chunks[0]['quantity_kg'], 3125.0)
        self.assertEqual(chunks[0]['chunk_index'], 1)
        self.assertEqual(chunks[0]['total_chunks'], 3)

        # Second chunk: 16:00 - 17:00 (5 palettes, 3125 kg)
        self.assertEqual(chunks[1]['start_time'], datetime.time(16, 0))
        self.assertEqual(chunks[1]['end_time'], datetime.time(17, 0))
        self.assertEqual(chunks[1]['palettes'], 5.0)
        self.assertEqual(chunks[1]['quantity_kg'], 3125.0)
        self.assertEqual(chunks[1]['chunk_index'], 2)

        # Third chunk: 17:00 - 18:00 (5 palettes, 3125 kg)
        self.assertEqual(chunks[2]['start_time'], datetime.time(17, 0))
        self.assertEqual(chunks[2]['end_time'], datetime.time(18, 0))
        self.assertEqual(chunks[2]['palettes'], 5.0)
        self.assertEqual(chunks[2]['quantity_kg'], 3125.0)
        self.assertEqual(chunks[2]['chunk_index'], 3)

    def test_order_model_backward_chunking(self):
        # Order with 15 palettes equivalent (15 * 625 = 9375 kg)
        order = Order.objects.create(
            user=self.customer,
            pickup_time=datetime.time(18, 0),
            status='pending'
        )
        OrderItem.objects.create(
            order=order,
            menu_item=self.item,
            quantity=9375,
            status='pending'
        )

        chunks = split_order_into_hourly_chunks(order=order, settings=self.settings)
        self.assertEqual(len(chunks), 3)
        self.assertEqual(chunks[0]['start_time'], datetime.time(15, 0))
        self.assertEqual(chunks[1]['start_time'], datetime.time(16, 0))
        self.assertEqual(chunks[2]['start_time'], datetime.time(17, 0))
        self.assertEqual(chunks[0]['order_id'], order.id)

    def test_partial_palette_chunking(self):
        # 12 palettes with 5 palettes/hr, pickup 17:00 -> [5.0, 5.0, 2.0] at 14:00, 15:00, 16:00
        chunks = split_order_into_hourly_chunks(
            palettes_count=12.0,
            pickup_time=datetime.time(17, 0),
            palettes_per_hour=5.0,
            kg_per_palette=500.0
        )
        self.assertEqual(len(chunks), 3)
        self.assertEqual(chunks[0]['start_time'], datetime.time(14, 0))
        self.assertEqual(chunks[0]['palettes'], 5.0)
        self.assertEqual(chunks[1]['start_time'], datetime.time(15, 0))
        self.assertEqual(chunks[1]['palettes'], 5.0)
        self.assertEqual(chunks[2]['start_time'], datetime.time(16, 0))
        self.assertEqual(chunks[2]['palettes'], 2.0)

    def test_production_dashboard_view_renders_queue(self):
        order = Order.objects.create(
            user=self.customer,
            pickup_time=datetime.time(18, 0),
            status='pending'
        )
        OrderItem.objects.create(
            order=order,
            menu_item=self.item,
            quantity=9375,
            status='pending'
        )

        self.client.login(username='worker_willy', password='workerpassword')
        resp = self.client.get(reverse('production_dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('hourly_tasks', resp.context)
        self.assertIn('current_task', resp.context)
        self.assertIn('upcoming_tasks', resp.context)

        self.assertEqual(len(resp.context['hourly_tasks']), 3)
        self.assertEqual(resp.context['current_task']['start_time_str'], "15:00")
        self.assertEqual(len(resp.context['upcoming_tasks']), 2)

        # Assert UI elements in template
        self.assertContains(resp, "Aktuelle Aufgabe")
        self.assertContains(resp, "Anstehende Aufgaben")
        self.assertContains(resp, "15:00 - 16:00")
        self.assertContains(resp, "Paletten")
        self.assertContains(resp, "3125")

    def test_all_future_chunks_visible_and_sorted_regardless_of_current_time(self):
        """
        Verify that ALL future chunks across active orders are always visible,
        never hidden based on the current time, and sorted strictly chronologically.
        """
        # Order 1: Pickup 14:00, 10 palettes (2 chunks: 12:00, 13:00)
        order1 = Order.objects.create(
            user=self.customer,
            pickup_time=datetime.time(14, 0),
            status='pending'
        )
        OrderItem.objects.create(
            order=order1,
            menu_item=self.item,
            quantity=6250,  # 10 palettes
            status='pending'
        )

        # Order 2: Pickup 18:00, 15 palettes (3 chunks: 15:00, 16:00, 17:00)
        order2 = Order.objects.create(
            user=self.customer,
            pickup_time=datetime.time(18, 0),
            status='pending'
        )
        OrderItem.objects.create(
            order=order2,
            menu_item=self.item,
            quantity=9375,  # 15 palettes
            status='pending'
        )

        tasks = get_production_tasks(settings=self.settings)
        # All 5 chunks must be present
        self.assertEqual(len(tasks), 5)

        # Strict chronological order: 12:00, 13:00, 15:00, 16:00, 17:00
        self.assertEqual(tasks[0]['start_time_str'], "12:00")
        self.assertTrue(tasks[0]['is_current'])
        self.assertEqual(tasks[0]['order_id'], order1.id)

        self.assertEqual(tasks[1]['start_time_str'], "13:00")
        self.assertFalse(tasks[1]['is_current'])
        self.assertEqual(tasks[1]['order_id'], order1.id)

        self.assertEqual(tasks[2]['start_time_str'], "15:00")
        self.assertFalse(tasks[2]['is_current'])
        self.assertEqual(tasks[2]['order_id'], order2.id)

        self.assertEqual(tasks[3]['start_time_str'], "16:00")
        self.assertFalse(tasks[3]['is_current'])
        self.assertEqual(tasks[3]['order_id'], order2.id)

        self.assertEqual(tasks[4]['start_time_str'], "17:00")
        self.assertFalse(tasks[4]['is_current'])
        self.assertEqual(tasks[4]['order_id'], order2.id)

        # View rendering checks
        self.client.login(username='worker_willy', password='workerpassword')
        resp = self.client.get(reverse('production_dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context['hourly_tasks']), 5)
        self.assertEqual(resp.context['current_task']['start_time_str'], "12:00")
        self.assertEqual(len(resp.context['upcoming_tasks']), 4)


    def test_continuous_backward_scheduling_across_midnight(self):
        """
        Verify backward scheduling across midnight into the previous calendar day:
        15 palettes, 5 palettes/hr -> 3 chunks.
        Pickup at 02:00 on 2026-08-25:
          - Chunk 1: 2026-08-24 23:00 - 00:00 (5 palettes, target_date=2026-08-24)
          - Chunk 2: 2026-08-25 00:00 - 01:00 (5 palettes, target_date=2026-08-25)
          - Chunk 3: 2026-08-25 01:00 - 02:00 (5 palettes, target_date=2026-08-25)
        """
        target_date = datetime.date(2026, 8, 25)
        chunks = split_order_into_hourly_chunks(
            palettes_count=15.0,
            pickup_time=datetime.time(2, 0),
            target_date=target_date,
            palettes_per_hour=5.0,
            kg_per_palette=625.0
        )
        self.assertEqual(len(chunks), 3)

        # Chunk 1 on previous day 2026-08-24
        self.assertEqual(chunks[0]['target_date'], datetime.date(2026, 8, 24))
        self.assertEqual(chunks[0]['start_time'], datetime.time(23, 0))
        self.assertEqual(chunks[0]['end_time'], datetime.time(0, 0))
        self.assertEqual(chunks[0]['start_time_str'], "23:00")
        self.assertEqual(chunks[0]['end_time_str'], "00:00")
        self.assertEqual(chunks[0]['palettes'], 5.0)

        # Chunk 2 on target day 2026-08-25
        self.assertEqual(chunks[1]['target_date'], datetime.date(2026, 8, 25))
        self.assertEqual(chunks[1]['start_time'], datetime.time(0, 0))
        self.assertEqual(chunks[1]['end_time'], datetime.time(1, 0))
        self.assertEqual(chunks[1]['palettes'], 5.0)

        # Chunk 3 on target day 2026-08-25
        self.assertEqual(chunks[2]['target_date'], datetime.date(2026, 8, 25))
        self.assertEqual(chunks[2]['start_time'], datetime.time(1, 0))
        self.assertEqual(chunks[2]['end_time'], datetime.time(2, 0))
        self.assertEqual(chunks[2]['palettes'], 5.0)

    def test_production_dashboard_before_cutoff_shows_today_only(self):
        """
        Before cut_off_time (e.g. 14:00 < 22:00), the dashboard only shows tasks scheduled for today.
        """
        today = datetime.date(2026, 8, 25)
        tomorrow = datetime.date(2026, 8, 26)

        # Order 1 for today (pickup 18:00, 1 chunk at 17:00)
        order_today = Order.objects.create(
            user=self.customer,
            pickup_time=datetime.time(18, 0),
            status='pending'
        )
        order_today.created_at = timezone.make_aware(datetime.datetime.combine(today, datetime.time(10, 0)))
        order_today.save()
        OrderItem.objects.create(
            order=order_today,
            menu_item=self.item,
            quantity=3125,  # 5 palettes
            status='pending'
        )

        # Order 2 for tomorrow (pickup 10:00, 1 chunk at 09:00)
        order_tomorrow = Order.objects.create(
            user=self.customer,
            pickup_time=datetime.time(10, 0),
            status='pending'
        )
        order_tomorrow.created_at = timezone.make_aware(datetime.datetime.combine(tomorrow, datetime.time(7, 0)))
        order_tomorrow.save()
        OrderItem.objects.create(
            order=order_tomorrow,
            menu_item=self.item,
            quantity=3125,  # 5 palettes
            status='pending'
        )

        self.client.login(username='worker_willy', password='workerpassword')

        # Mock current time as today at 14:00 (before 22:00 cutoff)
        mock_now = timezone.make_aware(datetime.datetime.combine(today, datetime.time(14, 0)))
        with patch('django.utils.timezone.now', return_value=mock_now):
            resp = self.client.get(reverse('production_dashboard'))
            self.assertEqual(resp.status_code, 200)
            self.assertFalse(resp.context['is_after_cutoff'])
            # Only today's chunk should be displayed
            self.assertEqual(len(resp.context['hourly_tasks']), 1)
            self.assertEqual(resp.context['hourly_tasks'][0]['order_id'], order_today.id)
            self.assertEqual(resp.context['hourly_tasks'][0]['start_time_str'], "17:00")

    def test_production_dashboard_after_cutoff_shows_today_and_tomorrow_merged(self):
        """
        After cut_off_time (e.g. 22:15 >= 22:00), the dashboard fetches both today and tomorrow tasks,
        merging and sorting them strictly chronologically.
        """
        today = datetime.date(2026, 8, 25)
        tomorrow = datetime.date(2026, 8, 26)

        # Order 1 for today: Pickup 23:00 (chunk at 22:00)
        order_today = Order.objects.create(
            user=self.customer,
            pickup_time=datetime.time(23, 0),
            status='pending'
        )
        order_today.created_at = timezone.make_aware(datetime.datetime.combine(today, datetime.time(10, 0)))
        order_today.save()
        OrderItem.objects.create(
            order=order_today,
            menu_item=self.item,
            quantity=3125,  # 5 palettes
            status='pending'
        )

        # Order 2 for tomorrow: Pickup 08:00 (chunk at 07:00)
        order_tomorrow = Order.objects.create(
            user=self.customer,
            pickup_time=datetime.time(8, 0),
            status='pending'
        )
        order_tomorrow.created_at = timezone.make_aware(datetime.datetime.combine(tomorrow, datetime.time(5, 0)))
        order_tomorrow.save()
        OrderItem.objects.create(
            order=order_tomorrow,
            menu_item=self.item,
            quantity=3125,  # 5 palettes
            status='pending'
        )

        self.client.login(username='worker_willy', password='workerpassword')

        # Mock current time as today at 22:15 (after 22:00 cutoff)
        mock_now = timezone.make_aware(datetime.datetime.combine(today, datetime.time(22, 15)))
        with patch('django.utils.timezone.now', return_value=mock_now):
            resp = self.client.get(reverse('production_dashboard'))
            self.assertEqual(resp.status_code, 200)
            self.assertTrue(resp.context['is_after_cutoff'])
            # Both today and tomorrow chunks should be displayed (2 tasks total)
            self.assertEqual(len(resp.context['hourly_tasks']), 2)
            # Strict chronological sort
            self.assertEqual(resp.context['hourly_tasks'][0]['order_id'], order_today.id)
            self.assertEqual(resp.context['hourly_tasks'][0]['target_date'], today)
            self.assertEqual(resp.context['hourly_tasks'][0]['start_time_str'], "22:00")
            self.assertTrue(resp.context['hourly_tasks'][0]['is_current'])

            self.assertEqual(resp.context['hourly_tasks'][1]['order_id'], order_tomorrow.id)
            self.assertEqual(resp.context['hourly_tasks'][1]['target_date'], tomorrow)
            self.assertEqual(resp.context['hourly_tasks'][1]['start_time_str'], "07:00")
            self.assertFalse(resp.context['hourly_tasks'][1]['is_current'])


class HourlyAvailabilityTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.customer = CustomUser.objects.create_user(
            username='anna_kunde',
            email='anna@kunde.de',
            password='customerpass',
            role='customer',
            is_approved=True
        )
        self.settings = FactorySettings.get_settings()
        self.settings.palettes_per_hour = 5.0
        self.settings.kg_per_palette = 625.0
        self.settings.buro_working_start = datetime.time(8, 0)
        self.settings.buro_working_end = datetime.time(17, 0)
        self.settings.production_working_start = datetime.time(6, 0)
        self.settings.production_working_end = datetime.time(22, 0)
        self.settings.save()

        self.item = MenuItem.objects.create(
            name='Laura Gar 4kg',
            produkt_type='Gar',
            verfügbar=True
        )

    def test_empty_day_availability(self):
        """
        Verify that get_hourly_availability generates a complete 24-hour slot list
        (00:00 to 23:59 -> 24 slots) ignoring any shift boundaries.
        """
        target_date = datetime.date(2026, 8, 20)
        slots = get_hourly_availability(target_date=target_date, settings=self.settings)

        # Full 24-hour slots list (00:00 through 23:00)
        self.assertEqual(len(slots), 24)
        self.assertEqual(slots[0]['time'], "00:00 - 01:00")
        self.assertEqual(slots[0]['start_str'], "00:00")
        self.assertEqual(slots[0]['end_str'], "01:00")
        self.assertEqual(slots[23]['time'], "23:00 - 00:00")
        self.assertEqual(slots[23]['start_str'], "23:00")
        self.assertEqual(slots[23]['end_str'], "00:00")

        # In an empty day, all 24 slots have used=0, remaining=5.0, status='free'
        for slot in slots:
            self.assertEqual(slot['total'], 5.0)
            self.assertEqual(slot['used'], 0.0)
            self.assertEqual(slot['remaining'], 5.0)
            self.assertEqual(slot['status'], 'free')
            self.assertEqual(slot['badge_class'], 'success')

    def test_24_hour_availability_ignores_shifts(self):
        """
        Verify that changing office or production shift start/end hours does not alter
        the 24-hour slot generation or hourly capacity.
        """
        self.settings.buro_working_start = datetime.time(10, 0)
        self.settings.buro_working_end = datetime.time(16, 0)
        self.settings.production_working_start = datetime.time(8, 0)
        self.settings.production_working_end = datetime.time(18, 0)
        self.settings.palettes_per_hour = 3.5
        self.settings.save()

        target_date = datetime.date(2026, 8, 22)
        slots = get_hourly_availability(target_date=target_date, settings=self.settings)

        self.assertEqual(len(slots), 24)
        for slot in slots:
            self.assertEqual(slot['total'], 3.5)
            self.assertEqual(slot['remaining'], 3.5)
            self.assertEqual(slot['status'], 'free')

    def test_scheduled_order_subtracts_from_slots(self):
        target_date = datetime.date(2026, 8, 20)

        # Create an order with pickup at 16:00, requiring 8 palettes (5 at 15:00-16:00, 3 at 14:00-15:00)
        order = Order.objects.create(
            user=self.customer,
            pickup_time=datetime.time(16, 0),
            status='pending'
        )
        order.created_at = timezone.make_aware(datetime.datetime.combine(target_date, datetime.time(9, 0)))
        order.save()

        OrderItem.objects.create(
            order=order,
            menu_item=self.item,
            quantity=5000,  # 8 palettes * 625kg = 5000kg
            status='pending'
        )

        slots = get_hourly_availability(target_date=target_date, settings=self.settings)
        self.assertEqual(len(slots), 24)
        slots_by_time = {s['time']: s for s in slots}

        # 14:00 - 15:00: used=5.0, remaining=0.0 (full)
        self.assertIn('14:00 - 15:00', slots_by_time)
        slot_14 = slots_by_time['14:00 - 15:00']
        self.assertEqual(slot_14['used'], 5.0)
        self.assertEqual(slot_14['remaining'], 0.0)
        self.assertEqual(slot_14['status'], 'full')
        self.assertEqual(slot_14['badge_class'], 'danger')

        # 15:00 - 16:00: used=3.0, remaining=2.0 (partial)
        self.assertIn('15:00 - 16:00', slots_by_time)
        slot_15 = slots_by_time['15:00 - 16:00']
        self.assertEqual(slot_15['used'], 3.0)
        self.assertEqual(slot_15['remaining'], 2.0)
        self.assertEqual(slot_15['status'], 'partial')
        self.assertEqual(slot_15['badge_class'], 'warning')

        # Other slots remain free (e.g. 00:00 - 01:00, 08:00 - 09:00, 23:00 - 00:00)
        slot_00 = slots_by_time['00:00 - 01:00']
        self.assertEqual(slot_00['used'], 0.0)
        self.assertEqual(slot_00['remaining'], 5.0)
        self.assertEqual(slot_00['status'], 'free')

        slot_23 = slots_by_time['23:00 - 00:00']
        self.assertEqual(slot_23['used'], 0.0)
        self.assertEqual(slot_23['remaining'], 5.0)
        self.assertEqual(slot_23['status'], 'free')

    def test_add_items_view_contains_hourly_availability_and_accepts_pickup_time(self):
        # Configure working hours to cover current time
        self.settings.buro_working_start = datetime.time(0, 0)
        self.settings.buro_working_end = datetime.time(23, 59)
        self.settings.save()

        order = Order.objects.create(
            user=self.customer,
            status='pending'
        )

        self.client.login(username='anna_kunde', password='customerpass')
        resp = self.client.get(reverse('add_items_to_order', args=[order.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('hourly_availability', resp.context)
        self.assertEqual(len(resp.context['hourly_availability']), 24)
        self.assertContains(resp, "Verfügbare Kapazitäten")
        self.assertContains(resp, "Gewünschte Abholzeit")

        # Post with specific pickup_time
        post_data = {
            'items': [str(self.item.id)],
            f'quantity_{self.item.id}': '1250',  # 2 palettes
            'pickup_time': '15:30',
        }
        post_resp = self.client.post(reverse('add_items_to_order', args=[order.id]), data=post_data)
        self.assertEqual(post_resp.status_code, 302)

        order.refresh_from_db()
        self.assertEqual(order.pickup_time, datetime.time(15, 30))


class GermanLanguageAndRoleChoicesTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin = CustomUser.objects.create_user(
            username='admin_hans',
            email='admin@kartoffeln.de',
            password='adminpass',
            role='admin',
            is_approved=True
        )
        self.worker = CustomUser.objects.create_user(
            username='worker_klaus',
            email='klaus@kartoffeln.de',
            password='workerpass',
            role='worker',
            is_approved=True
        )
        self.customer = CustomUser.objects.create_user(
            username='kunde_greta',
            email='greta@kartoffeln.de',
            password='kundenpass',
            role='customer',
            is_approved=True
        )

    def test_role_display_names_are_in_pure_german(self):
        self.assertEqual(self.admin.get_role_display(), 'Admin')
        self.assertEqual(self.worker.get_role_display(), 'Mitarbeiter')
        self.assertEqual(self.customer.get_role_display(), 'Kunde')

    def test_admin_users_view_renders_clean_german_without_uzbek_text(self):
        self.client.login(username='admin_hans', password='adminpass')
        resp = self.client.get(reverse('admin_users'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Personalverwaltung")
        self.assertContains(resp, "Mitarbeiter")
        self.assertContains(resp, "Kunde")
        self.assertNotContains(resp, "Mijoz")
        self.assertNotContains(resp, "Ishchi")
        self.assertNotContains(resp, "Tasdiqlash kutilmoqda")
        self.assertNotContains(resp, "Arhiv")





