from decimal import Decimal
import json

from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.urls import reverse

from .models import Customer, Product, Sale, SaleItem


class PosWorkflowTests(TestCase):
	def setUp(self):
		self.product = Product.objects.create(
			name="Rice",
			quantity=10,
			cost_price=Decimal("100.00"),
			selling_price=Decimal("150.00"),
		)

	def test_checkout_consolidates_cart_and_reduces_stock(self):
		response = self.client.post(
			reverse("mini_mart:new_sale"),
			{"cart": [f"{self.product.pk}:2", f"{self.product.pk}:3"]},
		)

		sale = Sale.objects.get()
		self.assertRedirects(response, reverse("mini_mart:record_payment", args=[sale.pk]))
		self.assertEqual(sale.total_amount, Decimal("750.00"))
		self.assertEqual(sale.items.get().quantity, 5)
		self.assertEqual(Product.objects.get(pk=self.product.pk).quantity, 5)

	def test_checkout_rejects_insufficient_stock_without_creating_sale(self):
		response = self.client.post(
			reverse("mini_mart:new_sale"),
			{"cart": [f"{self.product.pk}:11"]},
		)

		self.assertRedirects(response, reverse("mini_mart:new_sale"))
		self.assertFalse(Sale.objects.exists())
		self.assertEqual(Product.objects.get(pk=self.product.pk).quantity, 10)

	def test_payment_rejects_overpayment(self):
		sale = Sale.objects.create(
			total_amount=Decimal("150.00"),
			cost_amount=Decimal("100.00"),
		)

		response = self.client.post(
			reverse("mini_mart:record_payment", args=[sale.pk]),
			{"amount": "151.00", "discount_amount": "0"},
		)

		sale.refresh_from_db()
		self.assertEqual(sale.amount_paid, Decimal("0.00"))
		self.assertEqual(response.status_code, 200)

	def test_customer_debt_views_use_sale_balances(self):
		customer = Customer.objects.create(name="Ada")
		Sale.objects.create(
			customer=customer,
			total_amount=Decimal("150.00"),
			cost_amount=Decimal("100.00"),
		)

		response = self.client.get(reverse("mini_mart:debts_hub"))

		self.assertContains(response, "₦150.00")
		self.assertEqual(response.context["total_outstanding"], Decimal("150.00"))

	def test_debts_hub_search_matches_customer_name_or_phone(self):
		matching_customer = Customer.objects.create(name="Ada Lovelace", phone_number="08012345678")
		other_customer = Customer.objects.create(name="Grace Hopper", phone_number="09087654321")
		for customer in (matching_customer, other_customer):
			Sale.objects.create(
				customer=customer,
				total_amount=Decimal("150.00"),
				cost_amount=Decimal("100.00"),
			)

		name_response = self.client.get(reverse("mini_mart:debts_hub"), {"q": "lovelace"})
		phone_response = self.client.get(reverse("mini_mart:debts_hub"), {"q": "09087654321"})

		self.assertEqual(list(name_response.context["debtors"]), [matching_customer])
		self.assertEqual(list(phone_response.context["debtors"]), [other_customer])

	def test_sales_history_search_matches_product_name(self):
		sale = Sale.objects.create(
			total_amount=Decimal("150.00"),
			cost_amount=Decimal("100.00"),
		)
		SaleItem.objects.create(
			sale=sale,
			product=self.product,
			quantity=1,
			unit_price=Decimal("150.00"),
		)

		response = self.client.get(reverse("mini_mart:sales_history"), {"q": "rice"})

		self.assertEqual(response.status_code, 200)
		self.assertIn(sale, response.context["sales"])

	def test_product_with_sale_history_cannot_be_deleted(self):
		sale = Sale.objects.create(
			total_amount=Decimal("150.00"),
			cost_amount=Decimal("100.00"),
		)
		SaleItem.objects.create(
			sale=sale,
			product=self.product,
			quantity=1,
			unit_price=Decimal("150.00"),
		)

		with self.assertRaises(ProtectedError):
			self.product.delete()

	def test_offline_sale_sync_records_paid_sale_and_reduces_stock(self):
		response = self.client.post(
			reverse("mini_mart:sync_offline_sale"),
			data=json.dumps({"items": [{"product_id": self.product.pk, "quantity": 2}]}),
			content_type="application/json",
		)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.json()["status"], "synced")
		sale = Sale.objects.get()
		self.assertEqual(sale.amount_paid, Decimal("300.00"))
		self.assertEqual(Product.objects.get(pk=self.product.pk).quantity, 8)

	def test_offline_sale_sync_rejects_insufficient_stock(self):
		response = self.client.post(
			reverse("mini_mart:sync_offline_sale"),
			data=json.dumps({"items": [{"product_id": self.product.pk, "quantity": 11}]}),
			content_type="application/json",
		)

		self.assertEqual(response.status_code, 400)
		self.assertFalse(Sale.objects.exists())
		self.assertEqual(Product.objects.get(pk=self.product.pk).quantity, 10)
