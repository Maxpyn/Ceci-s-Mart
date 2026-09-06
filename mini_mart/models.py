from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.deletion import PROTECT


class Product(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    quantity = models.PositiveIntegerField(default=0)
    initial_quantity = models.PositiveIntegerField(default=0)
    cost_price = models.DecimalField(max_digits=10, decimal_places=2)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2)
    date_added = models.DateTimeField(auto_now_add=True)
    is_available = models.BooleanField(default=True)

    @property
    def profit_per_unit(self):
        return self.selling_price - self.cost_price

    @property
    def stock_value(self):
        return self.quantity * self.selling_price

    @property
    def potential_revenue(self):
        return self.initial_quantity * self.selling_price

    @property
    def potential_profit(self):
        return self.initial_quantity * (self.selling_price - self.cost_price)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if self._state.adding and not self.initial_quantity:
            self.initial_quantity = self.quantity
        super().save(*args, **kwargs)


class Customer(models.Model):
    name = models.CharField(max_length=100)
    phone_number = models.CharField(max_length=15, blank=True)
    address = models.TextField(blank=True)

    outstanding_debt = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    @property
    def total_debt(self):
        sale_debt = sum(s.balance for s in self.sale_set.filter(balance__gt=0))
        existing_debt = sum(
            debt.balance for debt in self.existingdebt_set.filter(balance__gt=0)
        )
        return sale_debt + existing_debt

    @property
    def is_debtor(self):
        return self.total_debt > 0

    def __str__(self):
        return self.name


class ExistingDebt(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    description = models.CharField(max_length=200, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    amount_paid = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    balance = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        editable=False,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        if self.amount <= 0:
            raise ValidationError("Debt amount must be greater than zero.")
        if self.amount_paid < 0 or self.amount_paid > self.amount:
            raise ValidationError("Amount paid must be between zero and the debt amount.")

    def save(self, *args, **kwargs):
        self.balance = self.amount - self.amount_paid
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Debt for {self.customer}"


class Sale(models.Model):
    customer = models.ForeignKey(
        Customer,
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    )

    total_amount = models.DecimalField(max_digits=12, decimal_places=2)  
    cost_amount = models.DecimalField(max_digits=12, decimal_places=2)  

    discount_amount = models.DecimalField(  
        max_digits=12,  
        decimal_places=2,  
        default=Decimal("0.00"),  
    )  

    final_amount = models.DecimalField(  
        max_digits=12,  
        decimal_places=2,  
        editable=False,  
    )  

    profit = models.DecimalField(  
        max_digits=12,  
        decimal_places=2,  
        editable=False,  
    )  

    amount_paid = models.DecimalField(  
        max_digits=12,  
        decimal_places=2,  
        default=Decimal("0.00"),  
    )  

    balance = models.DecimalField(  
        max_digits=12,  
        decimal_places=2,  
        default=Decimal("0.00"),  
        editable=False,  
    )  

    is_paid = models.BooleanField(  
        default=False,  
        editable=False,  
    )  

    created_at = models.DateTimeField(auto_now_add=True)  

    def clean(self):  
        if self.discount_amount > self.total_amount:  
            raise ValidationError(  
                "Discount cannot be greater than total amount."  
            )  

    def save(self, *args, **kwargs):
        self.final_amount = self.total_amount - self.discount_amount  
        self.profit = self.final_amount - self.cost_amount  
        self.balance = self.final_amount - self.amount_paid  
        self.is_paid = self.balance <= 0  

        super().save(*args, **kwargs)

    @property
    def is_credit(self):
        return self.balance > 0

    def __str__(self):
        return f"Sale #{self.pk}"

class SaleItem(models.Model):
    sale = models.ForeignKey(
        Sale,
        on_delete=models.CASCADE,
        related_name="items",
    )

    product = models.ForeignKey(  
        Product,  
        on_delete=PROTECT,
    )  

    quantity = models.PositiveIntegerField()  

    unit_price = models.DecimalField(  
        max_digits=10,  
        decimal_places=2,  
    )  

    @property  
    def subtotal(self):  
        return self.quantity * self.unit_price  

    @property  
    def profit(self):  
        return (  
            (self.unit_price - self.product.cost_price)  
            * self.quantity  
        )  

    def __str__(self):
        return f"{self.quantity} x {self.product.name}"