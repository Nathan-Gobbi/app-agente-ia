# Copyright 2026 Nathan Gobbi
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    ai_assistant_openai_api_key = fields.Char(
        string="OpenAI API Key",
        config_parameter="ai_assistant.openai_api_key",
        groups="base.group_system",
        help="API key used by the Odoo AI Assistant. The OPENAI_API_KEY "
        "environment variable takes precedence when it is set.",
    )
    ai_assistant_openai_model = fields.Char(
        string="OpenAI Model",
        config_parameter="ai_assistant.openai_model",
        default="gpt-4.1-mini",
        groups="base.group_system",
        help="OpenAI model identifier used to answer questions.",
    )
