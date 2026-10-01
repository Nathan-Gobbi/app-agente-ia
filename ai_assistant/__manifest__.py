# Copyright 2026 Nathan Gobbi
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "Odoo AI Assistant",
    "summary": "Read-only AI assistant specialized in your Odoo ERP data",
    "version": "18.0.1.0.0",
    "category": "Productivity",
    "website": "https://github.com/Nathan-Gobbi/app-agente-ia",
    "author": "Nathan Gobbi",
    "maintainers": ["Nathan-Gobbi"],
    "license": "AGPL-3",
    "development_status": "Beta",
    "application": True,
    "installable": True,
    "depends": ["base_setup", "sale_stock"],
    "external_dependencies": {"python": ["pydantic-ai-slim[openai]>=1.0,<2.0"]},
    "data": [
        "security/ai_assistant_security.xml",
        "security/ir.model.access.csv",
        "views/res_config_settings_views.xml",
        "views/ai_assistant_conversation_views.xml",
        "views/ai_assistant_menus.xml",
    ],
}
