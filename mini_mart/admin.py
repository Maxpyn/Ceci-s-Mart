from django.contrib import admin

from .models import Product, Customer, Sale, SaleItem


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "selling_price",
        "quantity",
        "is_available",
    )
    list_filter = ("is_available",)
    search_fields = ("name",)
    ordering = ("name",)


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "phone_number",
        "address",
        "outstanding_debt",
    )
    search_fields = (
        "name",
        "phone_number",
        "address",
    )
    ordering = ("name",)


class SaleItemInline(admin.TabularInline):
    model = SaleItem
    extra = 0

    readonly_fields = (
        "product",
        "quantity",
        "unit_price",
        "line_total",
    )

    def line_total(self, obj):
        return obj.subtotal

    line_total.short_description = "Total"


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "customer_name",
        "total_amount",
        "discount_amount",
        "final_amount",
        "amount_paid",
        "balance",
        "profit",
        "is_paid",
        "created_at",
    )

    list_filter = (
        "is_paid",
        "created_at",
    )

    search_fields = (
        "id",
        "customer__name",
        "customer__phone_number",
    )

    readonly_fields = (
        "final_amount",
        "profit",
        "balance",
        "is_paid",
        "created_at",
    )

    date_hierarchy = "created_at"

    ordering = ("-created_at",)

    inlines = [SaleItemInline]

    @admin.display(description="Customer", ordering="customer__name")
    def customer_name(self, obj):
        return obj.customer.name if obj.customer else "Walk-in"

    def has_change_permission(self, request, obj=None):
        return obj is None or not obj.is_paid


@admin.register(SaleItem)
class SaleItemAdmin(admin.ModelAdmin):
    list_display = (
        "sale",
        "product",
        "quantity",
        "unit_price",
    )

    list_filter = (
        "product",
        "sale__created_at",
    )

    search_fields = (
        "sale__id",
        "product__name",
    )

    ordering = ("sale",)