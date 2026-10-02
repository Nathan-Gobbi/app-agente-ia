Go to **Settings > Odoo AI**, set the OpenAI API key and choose the model identifier.

Describe the business in **Business context** and enable only the read-only tools the
assistant should use. Product and sales tools activate only when their corresponding
Odoo apps and models are installed.

For deployments, prefer the `OPENAI_API_KEY` environment variable. It takes precedence
over the value stored in Odoo. The Odoo container must be allowed to reach
`api.openai.com`.
