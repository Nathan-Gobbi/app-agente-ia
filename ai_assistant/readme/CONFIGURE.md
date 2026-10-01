Go to **Settings > Odoo AI**, set the OpenAI API key and choose the model identifier.

For deployments, prefer the `OPENAI_API_KEY` environment variable. It takes precedence
over the value stored in Odoo. The Odoo container must be allowed to reach
`api.openai.com`.
