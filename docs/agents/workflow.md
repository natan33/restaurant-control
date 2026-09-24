# Workflow entre agentes

## Estados

`planned → investigating → implementing → verifying → reviewing → done`

Avance somente quando o estado atual tiver evidência suficiente. Em caso de bloqueio, permaneça no estado atual e devolva o motivo.

## Delegação Codex → OpenCode

```text
Objetivo:
Escopo:
Fora do escopo:
Arquivos/domínio:
Contexto relevante:
Perguntas:
Alterações permitidas:
Verificação:
Formato da saída:
Critério de conclusão:
```

O campo `Arquivos/domínio` reserva ownership temporário. Não delegue trabalho que sobreponha outro agente sem coordenação explícita.

## Handoff OpenCode → Codex

```text
Status:
Achados:
Arquivos:
Hipóteses/incertezas:
Alterações:
Testes/comandos:
Riscos:
Decisões necessárias:
Próximo passo:
```

O handoff deve distinguir fatos de hipóteses e incluir evidência reproduzível. Codex valida o resultado antes de implementar, integrar ou encerrar a etapa.

## Regra de comunicação

Continue. Seja econômico no relato e mostre apenas achados relevantes.
