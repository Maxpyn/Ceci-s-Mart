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

	def test_debtors_list_search_matches_customer_phone_sale_or_product(self):
		customer = Customer.objects.create(name="Ada Lovelace", phone_number="08023456789")
		other_customer = Customer.objects.create(name="Grace Hopper", phone_number="09087654320")
		other_product = Product.objects.create(
			name="Beans",
			quantity=10,
			cost_price=Decimal("80.00"),
			selling_price=Decimal("120.00"),
		)
		matching_sale = Sale.objects.create(
			customer=customer,
			total_amount=Decimal("150.00"),
			cost_amount=Decimal("100.00"),
		)
		other_sale = Sale.objects.create(
			customer=other_customer,
			total_amount=Decimal("200.00"),
			cost_amount=Decimal("120.00"),
		)
		SaleItem.objects.create(
			sale=matching_sale,
			product=self.product,
			quantity=1,
			unit_price=Decimal("150.00"),
		)
		SaleItem.objects.create(
			sale=other_sale,
			product=other_product,
			quantity=1,
			unit_price=Decimal("120.00"),
		)

		for query in ("lovelace", "08023456789", str(matching_sale.pk), "rice"):
			with self.subTest(query=query):
				response = self.client.get(reverse("mini_mart:debtors_list"), {"q": query})
				self.assertEqual(list(response.context["debts"]), [matching_sale])

		response = self.client.get(reverse("mini_mart:debtors_list"), {"q": "lovelace"})
		self.assertEqual(response.context["total_owed"], Decimal("150.00"))

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

	def test_sale_delete_restores_stock_and_removes_credit_from_history(self):
		customer = Customer.objects.create(name="Ada")
		sale = Sale.objects.create(
			customer=customer,
			total_amount=Decimal("300.00"),
			cost_amount=Decimal("200.00"),
		)
		SaleItem.objects.create(
			sale=sale,
			product=self.product,
			quantity=2,
			unit_price=Decimal("150.00"),
		)
		self.product.quantity = 8
		self.product.save(update_fields=["quantity"])

		response = self.client.post(reverse("mini_mart:sale_delete", args=[sale.pk]))

		self.assertRedirects(response, reverse("mini_mart:sales_list"))
		self.assertFalse(Sale.objects.filter(pk=sale.pk).exists())
		self.assertEqual(Product.objects.get(pk=self.product.pk).quantity, 10)
		self.assertEqual(
			Sale.objects.filter(customer=customer, balance__gt=0).count(),
			0,
		)

	def test_sale_delete_requires_post(self):
		sale = Sale.objects.create(
			total_amount=Decimal("150.00"),
			cost_amount=Decimal("100.00"),
		)

		response = self.client.get(reverse("mini_mart:sale_delete", args=[sale.pk]))

		self.assertEqual(response.status_code, 405)
		self.assertTrue(Sale.objects.filter(pk=sale.pk).exists())

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
