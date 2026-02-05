from .models import MenuItem,CustomUser
from rest_framework import serializers
from django.contrib.auth.hashers import make_password

class SignupSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ['username', 'password', 'first_name', 'last_name', 'email', 'role']

    def validate_role(self, value):
        if value not in ['admin', 'worker', 'customer']:
            raise serializers.ValidationError("Noto‘g‘ri rol")
        return value

    def validate_password(self, value):
        if len(value) < 6:
            raise serializers.ValidationError("Parol kamida 6 ta belgidan iborat bo‘lishi kerak")
        return value

    def create(self, validated_data):
        validated_data['password'] = make_password(validated_data['password'])
        return CustomUser.objects.create(**validated_data)

class MenuItemSerializer(serializers.ModelSerializer):
    class Meta:
        model=MenuItem
        fields='__all__'


from rest_framework import serializers
from .models import Order, OrderItem, MenuItem

class MenuSerializer(serializers.ModelSerializer):
    class Meta:
        model = MenuItem
        fields = ['id', 'name', 'price']

class OrderItemSerializer(serializers.ModelSerializer):
    menu_item = MenuSerializer(read_only=True)
    menu_item_id = serializers.PrimaryKeyRelatedField(
        queryset=MenuItem.objects.all(), source='menu_item', write_only=True
    )

    class Meta:
        model = OrderItem
        fields = ['id', 'menu_item', 'menu_item_id', 'quantity', 'price']

class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, write_only=True)
    total_price = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = ['id', 'customer', 'created_at', 'status', 'items', 'total_price']
        read_only_fields = ['id', 'customer', 'created_at', 'total_price']

    def get_total_price(self, obj):
        return obj.calculate_total_price()

    def create(self, validated_data):
        items_data = validated_data.pop('items')
        order = Order.objects.create(customer=self.context['request'].user, **validated_data)
        for item_data in items_data:
            OrderItem.objects.create(order=order, **item_data)
        return order