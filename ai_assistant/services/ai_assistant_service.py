# Copyright 2026 Nathan Gobbi
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json
import os
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

import pytz

from odoo import _, api, models
from odoo.exceptions import UserError

SYSTEM_PROMPT = """You are a read-only data assistant specialized in the company's
Odoo ERP. Answer in the user's language, clearly and briefly. You must use the
provided tools for every factual claim about the company. Never invent records,
totals, SKUs, prices, or stock. Never claim that you changed data. Dates are
interpreted in the user's timezone. If the user omits the year, use the current year
and explicitly state that assumption. Sales mean confirmed sale orders only. Explain
which date range and metric were used. If a request is outside the available tools,
say what cannot be consulted instead of guessing. Tool availability depends on the
apps installed in this Odoo and on administrator settings. All queries are executed
with the current user's permissions and record rules.
"""


@dataclass
class AiAssistantDependencies:
    env: object
    timezone: str
    company_name: str


class AiAssistantService(models.AbstractModel):
    _name = "ai.assistant.service"
    _description = "Odoo AI Service"

    @api.model
    def answer(self, conversation, question):
        api_key = os.getenv("OPENAI_API_KEY") or self.env[
            "ir.config_parameter"
        ].sudo().get_param("ai_assistant.openai_api_key")
        if not api_key:
            raise UserError(
                _(
                    "Configure an OpenAI API key in Settings or set the "
                    "OPENAI_API_KEY environment variable."
                )
            )
        model_name = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("ai_assistant.openai_model", "gpt-4.1-mini")
        )
        try:
            from pydantic_ai import Agent, RunContext
            from pydantic_ai.models.openai import OpenAIModel
            from pydantic_ai.providers.openai import OpenAIProvider
        except ImportError as error:
            raise UserError(
                _("The pydantic-ai dependency is not installed.")
            ) from error

        dependencies = AiAssistantDependencies(
            env=self.env,
            timezone=self.env.user.tz or "UTC",
            company_name=conversation.company_id.display_name,
        )
        model = OpenAIModel(
            model_name,
            provider=OpenAIProvider(api_key=api_key),
        )
        agent = Agent(
            model,
            deps_type=AiAssistantDependencies,
            system_prompt=(
                f"{SYSTEM_PROMPT}\nToday is {date.today().isoformat()}. "
                f"Company: {dependencies.company_name}. "
                f"Timezone: {dependencies.timezone}. "
                f"Business context: {self._business_context()}"
            ),
        )
        self._register_tools(agent, RunContext)
        history = [
            {"role": message.role, "content": message.content}
            for message in conversation.message_ids[-10:]
        ]
        prompt = json.dumps(
            {"recent_conversation": history, "new_question": question},
            ensure_ascii=False,
        )
        result = agent.run_sync(prompt, deps=dependencies)
        return result.output

    @api.model
    def _business_context(self):
        return (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(
                "ai_assistant.business_context",
                "No additional business context was configured.",
            )
        )

    @api.model
    def _setting_enabled(self, key, default=True):
        value = self.env["ir.config_parameter"].sudo().get_param(key)
        if value in (False, None, ""):
            return default
        return str(value).lower() in {"1", "true", "yes", "on"}

    @api.model
    def _model_available(self, model_name):
        return model_name in self.env.registry.models

    @api.model
    def _register_tools(self, agent, run_context_class):
        """Register tools that are enabled and available in this Odoo registry.

        Extension addons can inherit this method, call ``super()``, and register
        tools for their own business models. Tools must use ``ctx.deps.env`` so
        Odoo access rights and record rules remain in force.
        """
        product_enabled = self._setting_enabled("ai_assistant.enable_product_tool")
        if product_enabled and self._model_available("product.product"):

            @agent.tool
            def find_products(
                ctx: run_context_class[AiAssistantDependencies],
                query: str,
                limit: int = 10,
            ) -> str:
                """Find products by name, SKU, or barcode and return sale prices.

                Stock on hand and forecast quantities are also returned when the
                Inventory app provides those fields.
                """
                return self._find_products(ctx.deps, query, limit)

        sales_enabled = self._setting_enabled("ai_assistant.enable_sales_tool")
        sales_available = self._model_available("sale.order") and self._model_available(
            "sale.order.line"
        )
        if sales_enabled and sales_available:

            @agent.tool
            def top_selling_products(
                ctx: run_context_class[AiAssistantDependencies],
                start_date: date,
                end_date: date | None = None,
                limit: int = 5,
            ) -> str:
                """Rank products sold in an inclusive local date range."""
                return self._top_selling_products(
                    ctx.deps, start_date, end_date or start_date, limit
                )

            @agent.tool
            def sales_summary(
                ctx: run_context_class[AiAssistantDependencies],
                start_date: date,
                end_date: date | None = None,
            ) -> str:
                """Return confirmed sales totals for an inclusive local date range."""
                return self._sales_summary(ctx.deps, start_date, end_date or start_date)

        return agent

    @api.model
    def _date_domain(self, dependencies, start_date, end_date):
        if end_date < start_date:
            raise ValueError("end_date must be on or after start_date")
        timezone = pytz.timezone(dependencies.timezone)
        local_start = timezone.localize(datetime.combine(start_date, time.min))
        local_end = timezone.localize(
            datetime.combine(end_date + timedelta(days=1), time.min)
        )
        return [
            (
                "order_id.date_order",
                ">=",
                local_start.astimezone(pytz.UTC).replace(tzinfo=None),
            ),
            (
                "order_id.date_order",
                "<",
                local_end.astimezone(pytz.UTC).replace(tzinfo=None),
            ),
        ]

    @api.model
    def _top_selling_products(self, dependencies, start_date, end_date, limit=5):
        limit = max(1, min(int(limit), 20))
        domain = self._date_domain(dependencies, start_date, end_date) + [
            ("order_id.state", "in", ["sale", "done"]),
            ("order_id.company_id", "=", dependencies.env.company.id),
            ("display_type", "=", False),
            ("product_id", "!=", False),
        ]
        groups = dependencies.env["sale.order.line"].read_group(
            domain,
            ["product_uom_qty:sum", "price_subtotal:sum"],
            ["product_id"],
            limit=limit,
            orderby="product_uom_qty desc",
            lazy=False,
        )
        products = (
            dependencies.env["product.product"]
            .browse([group["product_id"][0] for group in groups])
            .exists()
        )
        product_by_id = {product.id: product for product in products}
        rows = []
        for group in groups:
            product = product_by_id.get(group["product_id"][0])
            if not product:
                continue
            rows.append(
                {
                    "sku": product.default_code or "sem SKU",
                    "product": product.display_name,
                    "quantity": group["product_uom_qty"],
                    "untaxed_revenue": group["price_subtotal"],
                }
            )
        return json.dumps(
            {
                "period": [start_date.isoformat(), end_date.isoformat()],
                "ranking_metric": "ordered quantity",
                "results": rows,
            },
            ensure_ascii=False,
        )

    @api.model
    def _sales_summary(self, dependencies, start_date, end_date):
        line_domain = self._date_domain(dependencies, start_date, end_date) + [
            ("order_id.state", "in", ["sale", "done"]),
            ("order_id.company_id", "=", dependencies.env.company.id),
            ("display_type", "=", False),
        ]
        groups = dependencies.env["sale.order.line"].read_group(
            line_domain,
            ["product_uom_qty:sum", "price_subtotal:sum"],
            [],
            lazy=False,
        )
        totals = groups[0] if groups else {}
        order_domain = [
            ("state", "in", ["sale", "done"]),
            ("company_id", "=", dependencies.env.company.id),
        ]
        for field_name, operator, value in self._date_domain(
            dependencies, start_date, end_date
        ):
            order_domain.append((field_name.removeprefix("order_id."), operator, value))
        return json.dumps(
            {
                "period": [start_date.isoformat(), end_date.isoformat()],
                "confirmed_orders": dependencies.env["sale.order"].search_count(
                    order_domain
                ),
                "ordered_quantity": totals.get("product_uom_qty", 0.0),
                "untaxed_revenue": totals.get("price_subtotal", 0.0),
            },
            ensure_ascii=False,
        )

    @api.model
    def _find_products(self, dependencies, query, limit=10):
        limit = max(1, min(int(limit), 20))
        query = (query or "").strip()
        if len(query) < 2:
            raise ValueError("query must have at least two characters")
        product_model = dependencies.env["product.product"]
        available_fields = product_model.fields_get()
        search_fields = [
            field_name
            for field_name in ("default_code", "barcode", "name")
            if field_name in available_fields
        ]
        conditions = [(field_name, "ilike", query) for field_name in search_fields]
        domain = ["|"] * (len(conditions) - 1) + conditions
        products = product_model.search(domain, limit=limit)
        currency = dependencies.env.company.currency_id
        rows = []
        for product in products:
            rows.append(
                {
                    "sku": (
                        product.default_code or "sem SKU"
                        if "default_code" in available_fields
                        else ""
                    ),
                    "barcode": (
                        product.barcode or "" if "barcode" in available_fields else ""
                    ),
                    "product": product.display_name,
                    "sale_price": (
                        product.lst_price if "lst_price" in available_fields else None
                    ),
                    "currency": currency.name,
                    "on_hand": (
                        product.qty_available
                        if "qty_available" in available_fields
                        else None
                    ),
                    "forecast": (
                        product.virtual_available
                        if "virtual_available" in available_fields
                        else None
                    ),
                }
            )
        return json.dumps(rows, ensure_ascii=False)
