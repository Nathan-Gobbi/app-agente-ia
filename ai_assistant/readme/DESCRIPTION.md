This module adds a read-only AI assistant that can be installed in any Odoo 18
database, regardless of its business vertical.

The assistant uses typed tools backed by the Odoo ORM. Available tools are discovered
from installed Odoo apps and can be enabled by an administrator. Product searches
return sale prices and, when Inventory is installed, stock. Sales tools are available
only when Sales is installed.

Conversation records provide an audit trail. Every business query runs with the
current user's Odoo permissions, record rules, active company, and accessible fields.
Extension addons can register tools for their own business models.
