# Copyright 2026 Nathan Gobbi
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class AiAssistantConversation(models.Model):
    _name = "ai.assistant.conversation"
    _description = "Odoo AI Conversation"
    _order = "write_date desc, id desc"

    name = fields.Char(required=True, default=lambda self: _("New conversation"))
    user_id = fields.Many2one(
        "res.users",
        required=True,
        default=lambda self: self.env.user,
        readonly=True,
        index=True,
    )
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        readonly=True,
        index=True,
    )
    question = fields.Text(string="Your question", copy=False)
    message_ids = fields.One2many(
        "ai.assistant.message", "conversation_id", string="Messages", readonly=True
    )
    active = fields.Boolean(default=True)

    @api.constrains("user_id", "company_id")
    def _check_company_access(self):
        for conversation in self:
            if conversation.company_id not in conversation.user_id.company_ids:
                raise ValidationError(_("The user cannot access this company."))

    def action_ask(self):
        self.ensure_one()
        question = (self.question or "").strip()
        if not question:
            raise UserError(_("Write a question before asking the assistant."))
        if self.user_id != self.env.user:
            raise UserError(_("You can only use your own conversations."))

        self.env["ai.assistant.message"].create(
            {
                "conversation_id": self.id,
                "role": "user",
                "content": question,
            }
        )
        if self.name == _("New conversation"):
            self.name = question[:80]
        self.question = False

        try:
            answer = self.env["ai.assistant.service"].answer(self, question)
        except UserError:
            raise
        except Exception as error:
            raise UserError(
                _("The assistant could not answer right now. Try again later.")
            ) from error

        self.env["ai.assistant.message"].create(
            {
                "conversation_id": self.id,
                "role": "assistant",
                "content": answer,
            }
        )
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "current",
        }


class AiAssistantMessage(models.Model):
    _name = "ai.assistant.message"
    _description = "Odoo AI Message"
    _order = "id"

    conversation_id = fields.Many2one(
        "ai.assistant.conversation", required=True, ondelete="cascade", index=True
    )
    company_id = fields.Many2one(
        related="conversation_id.company_id", store=True, index=True
    )
    user_id = fields.Many2one(related="conversation_id.user_id", store=True, index=True)
    role = fields.Selection(
        [("user", "User"), ("assistant", "Assistant")], required=True, index=True
    )
    content = fields.Text(required=True)
