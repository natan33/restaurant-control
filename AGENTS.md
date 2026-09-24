# restaurant-control — regras de trabalho

## Contexto

Aplicação Flask com SQLAlchemy, PostgreSQL, Alembic/Flask-Migrate, Flask-Login, templates/Jinja e JavaScript. A evolução prevista é para SaaS multi-tenant. A suíte usa pytest ou unittest conforme os padrões já existentes.

## Regras do projeto

- Codex é o Tech Lead/orquestrador e mantém a decisão final sobre arquitetura, escopo e integração.
- Trabalhe em mudanças incrementais e não faça refatorações fora do escopo.
- Antes de modificar arquitetura, investigue as convenções existentes.
- Migrations devem preservar dados existentes; não apague dados históricos sem necessidade.
- Em mudanças multi-tenant, priorize o isolamento de dados. Toda query operacional deve considerar o tenant quando a entidade já for tenant-aware.
- Nunca confie somente em IDs vindos de sessão ou request para autorização; valide identidade, vínculo e permissão no servidor.
- Não permita trabalho concorrente no mesmo domínio sem coordenação explícita.
- Cada etapa concluída precisa de evidência adequada: testes, comandos, inspeção do diff ou outra verificação reproduzível.

## Escopo operacional

Use OpenCode principalmente para investigação, tarefas mecânicas, segunda opinião e revisão. Codex preserva seu limite de uso de 5 horas para arquitetura, implementação crítica, testes e revisão final.

Não faça commit, push, merge ou mudanças externas automaticamente. Consulte `docs/agents/codex-tech-lead.md`, `docs/agents/opencode-investigator.md` e `docs/agents/workflow.md` quando a tarefa envolver mais de um agente.
