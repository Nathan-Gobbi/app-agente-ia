# Copyright 2026 Nathan Gobbi
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json
import unittest
from datetime import date
from types import SimpleNamespace

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


class TestAiAssistantCore(TransactionCase):
    def test_conversation_belongs_to_current_user(self):
        conversation = self.env["ai.assistant.conversation"].create({})
        self.assertEqual(conversation.user_id, self.env.user)
        self.assertEqual(conversation.company_id, self.env.company)

    def test_optional_models_are_discovered(self):
        service = self.env["ai.assistant.service"]
        self.assertTrue(service._model_available("res.partner"))
        self.assertFalse(service._model_available("model.that.does.not.exist"))

    def test_disabled_tool_setting(self):
        parameters = self.env["ir.config_parameter"].sudo()
        parameters.set_param("ai_assistant.enable_product_tool", "False")
        self.assertFalse(
            self.env["ai.assistant.service"]._setting_enabled(
                "ai_assistant.enable_product_tool"
            )
        )


@tagged("post_install", "-at_install")
class TestAiAssistantOptionalSalesTools(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if "sale.order" not in cls.env.registry.models:
            raise unittest.SkipTest("Sales is not installed in this Odoo database")
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.service = cls.env["ai.assistant.service"]
        cls.partner = cls.env["res.partner"].create({"name": "AI Test Customer"})
        cls.product_a = cls.env["product.product"].create(
            {
                "name": "AI Test Chain",
                "default_code": "CHAIN-A",
                "list_price": 29.9,
                "is_storable": True,
            }
        )
        cls.product_b = cls.env["product.product"].create(
            {"name": "AI Test Tire", "default_code": "TIRE-B", "is_storable": True}
        )
        cls.order = cls.env["sale.order"].create(
            {
                "partner_id": cls.partner.id,
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
        cls.dependencies = SimpleNamespace(env=cls.env, timezone="America/Sao_Paulo")

    def test_find_product_returns_sale_price(self):
        result = json.loads(
            self.service._find_products(self.dependencies, "CHAIN-A", 5)
        )
        self.assertEqual(result[0]["sku"], "CHAIN-A")
        self.assertEqual(result[0]["sale_price"], 29.9)
        self.assertEqual(result[0]["currency"], self.env.company.currency_id.name)

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
