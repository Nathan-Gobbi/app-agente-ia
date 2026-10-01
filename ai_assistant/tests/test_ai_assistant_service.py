# Copyright 2026 Nathan Gobbi
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json
from datetime import date
from types import SimpleNamespace

from odoo.tests.common import TransactionCase


class TestAiAssistantService(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.service = cls.env["ai.assistant.service"]
        cls.partner = cls.env["res.partner"].create({"name": "AI Test Customer"})
        cls.product_a = cls.env["product.product"].create(
            {"name": "AI Test Chain", "default_code": "CHAIN-A", "is_storable": True}
        )
        cls.product_b = cls.env["product.product"].create(
            {"name": "AI Test Tire", "default_code": "TIRE-B", "is_storable": True}
        )
        cls.order = cls.env["sale.order"].create(
            {
                "partner_id": cls.partner.id,
                "date_order": "2026-06-25 15:00:00",
                "order_line": [
                    (
                        0,
                        0,
                        {
                            "product_id": cls.product_a.id,
                            "product_uom_qty": 4,
                            "price_unit": 20,
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "product_id": cls.product_b.id,
                            "product_uom_qty": 2,
                            "price_unit": 50,
                        },
                    ),
                ],
            }
        )
        cls.order.action_confirm()
        # Odoo replaces date_order with the confirmation timestamp.
        cls.order.date_order = "2026-06-25 15:00:00"
        cls.dependencies = SimpleNamespace(timezone="America/Sao_Paulo")

    def test_top_selling_products(self):
        result = json.loads(
            self.service._top_selling_products(
                self.dependencies, date(2026, 6, 25), date(2026, 6, 25), 5
            )
        )
        self.assertEqual(result["results"][0]["sku"], "CHAIN-A")
        self.assertEqual(result["results"][0]["quantity"], 4)

    def test_sales_summary(self):
        result = json.loads(
            self.service._sales_summary(
                self.dependencies, date(2026, 6, 25), date(2026, 6, 25)
            )
        )
        self.assertEqual(result["confirmed_orders"], 1)
        self.assertEqual(result["ordered_quantity"], 6)
        self.assertEqual(result["untaxed_revenue"], 180)

    def test_conversation_belongs_to_current_user(self):
        conversation = self.env["ai.assistant.conversation"].create({})
        self.assertEqual(conversation.user_id, self.env.user)
        self.assertEqual(conversation.company_id, self.env.company)
