# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe.utils import today

from erpnext.patches.v16_0.set_outstanding_for_zero_portion_payment_terms import execute
from erpnext.tests.utils import ERPNextTestSuite

PARENT_TYPES = ("Sales Invoice", "Purchase Invoice", "Sales Order", "Purchase Order")


class TestSetOutstandingForZeroPortionPaymentTerms(ERPNextTestSuite):
	def test_repairs_submitted_terms_and_is_idempotent(self):
		parent_name = frappe.generate_hash(length=10)
		terms = []
		for parenttype, conversion_rate in zip(PARENT_TYPES, (1, 1.25, 2, 80), strict=True):
			parent = self._make_parent(parenttype, conversion_rate=conversion_rate, name=parent_name)
			for paid_amount, discounted_amount in ((0, 0), (200, 50)):
				term = self._make_term(parent, paid_amount=paid_amount, discounted_amount=discounted_amount)
				terms.append((term, conversion_rate))

		execute()

		for term, conversion_rate in terms:
			with self.subTest(parenttype=term.parenttype, paid_amount=term.paid_amount):
				paid_amount, discounted_amount = term.paid_amount, term.discounted_amount
				term.reload()
				outstanding = 1000 - paid_amount - discounted_amount
				self.assertEqual(term.payment_amount, 1000)
				self.assertEqual(term.outstanding, outstanding)
				self.assertEqual(term.base_payment_amount, 1000 * conversion_rate)
				self.assertEqual(term.base_outstanding, outstanding * conversion_rate)
				self.assertEqual(term.paid_amount, paid_amount)
				self.assertEqual(term.discounted_amount, discounted_amount)
				self.assertEqual(term.invoice_portion, 0)

		snapshots = [term.as_dict() for term, _ in terms]
		execute()
		for (term, _), snapshot in zip(terms, snapshots, strict=True):
			self.assertEqual(term.reload().as_dict(), snapshot)

	def test_skips_ineligible_terms(self):
		terms = []
		for parenttype in PARENT_TYPES:
			for docstatus in (0, 2):
				terms.append(self._make_term(self._make_parent(parenttype, docstatus=docstatus)))

			parent = self._make_parent(parenttype)
			for values in (
				{"invoice_portion": 100},
				{"outstanding": 500},
				{"paid_amount": 1000},
				{"paid_amount": 950, "discounted_amount": 50},
				{"discounted_amount": 1000},
				{"paid_amount": 1100},
				{"payment_amount": 0},
				{"payment_amount": -1000},
			):
				terms.append(self._make_term(parent, **values))

		snapshots = [term.reload().as_dict() for term in terms]
		execute()
		for term, snapshot in zip(terms, snapshots, strict=True):
			with self.subTest(parenttype=term.parenttype, term=term.name):
				self.assertEqual(term.reload().as_dict(), snapshot)

	def test_skips_missing_parents_and_other_parent_types(self):
		parent = self._make_parent("Quotation")
		terms = [self._make_term(parent)]
		for parenttype in PARENT_TYPES:
			missing_parent = frappe.new_doc(parenttype)
			missing_parent.name = frappe.generate_hash(length=10)
			terms.append(self._make_term(missing_parent))

		snapshots = [term.reload().as_dict() for term in terms]
		execute()
		for term, snapshot in zip(terms, snapshots, strict=True):
			with self.subTest(parenttype=term.parenttype):
				self.assertEqual(term.reload().as_dict(), snapshot)

	def _make_parent(self, parenttype, docstatus=1, conversion_rate=2, name=None):
		parent = frappe.new_doc(parenttype)
		parent.update(
			{
				"name": name or frappe.generate_hash(length=10),
				"docstatus": docstatus,
				"conversion_rate": conversion_rate,
			}
		)
		parent.db_insert()
		return parent

	def _make_term(self, parent, **values):
		term = parent.append(
			"payment_schedule",
			{
				"due_date": today(),
				"invoice_portion": 0,
				"payment_amount": 1000,
				"paid_amount": 0,
				"discounted_amount": 0,
				"outstanding": 0,
				"base_payment_amount": 0,
				"base_outstanding": 0,
				**values,
			},
		)
		term.db_insert()
		return term
