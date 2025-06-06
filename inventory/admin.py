from django.contrib import admin
from .models import Supplier, Medicine, Batch, Order, OrderItem, StockTransaction

admin.site.register(Supplier)
admin.site.register(Medicine)
admin.site.register(Batch)
admin.site.register(Order)
admin.site.register(OrderItem)
admin.site.register(StockTransaction)