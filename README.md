# App Agente IA

Módulo independente para Odoo 18 que oferece um assistente de IA especializado nos
dados do ERP.

O agente consulta vendas, produtos e estoque por ferramentas tipadas e pelo ORM do
Odoo. Ele não recebe acesso a SQL, modelos arbitrários ou operações de escrita. As
consultas respeitam as permissões, empresas e regras de registro do usuário logado.

## Recursos

- Conversas persistentes com trilha de auditoria.
- Ranking de produtos e SKUs vendidos por data ou período.
- Resumo de pedidos confirmados, quantidade e receita sem impostos.
- Pesquisa de produtos, estoque disponível e previsto.
- Integração com OpenAI por meio do Pydantic AI.
- Testes automatizados para as ferramentas de consulta.

Consulte a documentação do addon em [`ai_assistant`](ai_assistant).

## Licença

AGPL-3.0-or-later.
