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
Odoo 18 ERP. Answer in Brazilian Portuguese, clearly and briefly.
You must use the provided tools for every factual claim about the company. Never
invent records, totals, SKUs or stock. Never claim that you changed data. Dates are
interpreted in the user's timezone. If the user omits the year, use the current year
and explicitly state that assumption. Sales mean confirmed sale orders only. Explain
which date range and metric were used. If a request is outside the available tools,
say what cannot be consulted instead of guessing.
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
                f"Timezone: {dependencies.timezone}."
            ),
        )

        @agent.tool
        def top_selling_products(
            ctx: RunContext[AiAssistantDependencies],
            start_date: date,
            end_date: date | None = None,
            limit: int = 5,
        ) -> str:
            """Rank products sold in a date or inclusive date range.

            Args:
                start_date: First local calendar date included.
                end_date: Last local calendar date included; defaults to start_date.
                limit: Maximum number of products, from 1 through 20.
            """
            return self._top_selling_products(
                ctx.deps, start_date, end_date or start_date, limit
            )

        @agent.tool
        def sales_summary(
            ctx: RunContext[AiAssistantDependencies],
            start_date: date,
            end_date: date | None = None,
        ) -> str:
            """Return confirmed sales totals for an inclusive local date range."""
            return self._sales_summary(ctx.deps, start_date, end_date or start_date)

        @agent.tool
        def find_products(
            ctx: RunContext[AiAssistantDependencies], query: str, limit: int = 10
        ) -> str:
            """Find products by SKU, barcode or name and return their stock."""
            return self._find_products(ctx.deps, query, limit)

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
            ("order_id.company_id", "=", self.env.company.id),
            ("display_type", "=", False),
            ("product_id", "!=", False),
        ]
        groups = self.env["sale.order.line"].read_group(
            domain,
            ["product_uom_qty:sum", "price_subtotal:sum"],
            ["product_id"],
            limit=limit,
            orderby="product_uom_qty desc",
            lazy=False,
        )
        products = (
            self.env["product.product"]
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
            ("order_id.company_id", "=", self.env.company.id),
            ("display_type", "=", False),
        ]
        groups = self.env["sale.order.line"].read_group(
            line_domain,
            ["product_uom_qty:sum", "price_subtotal:sum"],
            [],
            lazy=False,
        )
        totals = groups[0] if groups else {}
        order_domain = [
            ("state", "in", ["sale", "done"]),
            ("company_id", "=", self.env.company.id),
        ]
        for field_name, operator, value in self._date_domain(
            dependencies, start_date, end_date
        ):
            order_domain.append((field_name.removeprefix("order_id."), operator, value))
        return json.dumps(
            {
                "period": [start_date.isoformat(), end_date.isoformat()],
                "confirmed_orders": self.env["sale.order"].search_count(order_domain),
                "ordered_quantity": totals.get("product_uom_qty", 0.0),
                "untaxed_revenue": totals.get("price_subtotal", 0.0),
            },
            ensure_ascii=False,
        )

    @api.model
    def _find_products(self, dependencies, query, limit=10):
        del dependencies
        limit = max(1, min(int(limit), 20))
        query = (query or "").strip()
        if len(query) < 2:
            raise ValueError("query must have at least two characters")
        products = self.env["product.product"].search(
            [
                "|",
                "|",
                ("default_code", "ilike", query),
                ("barcode", "ilike", query),
                ("name", "ilike", query),
            ],
            limit=limit,
        )
        return json.dumps(
            [
                {
                    "sku": product.default_code or "sem SKU",
                    "barcode": product.barcode or "",
                    "product": product.display_name,
                    "on_hand": product.qty_available,
                    "forecast": product.virtual_available,
                }
                for product in products
            ],
            ensure_ascii=False,
        )
