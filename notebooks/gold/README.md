<a id="topo"></a>

# SQL analítico sobre a gold · os notebooks

[Home](../../README.md) | [Matriz de barramento](../../docs/15_matriz_de_barramento.md) | [Auditoria](../auditoria/README.md)

> Os notebooks da gold são a **Sala de Resultados** da fase 7: cada um lê a gold publicada no lake, roda as consultas declaradas em `rh_fictalent.gold.analitico` e deixa, ao lado de cada resultado, uma Nota Técnica (Observado, Por que importa, Ação). Seguem o mesmo padrão dos notebooks da auditoria: executados de cima a baixo num kernel novo, versionados com as saídas, com cabeçalho, Nota Técnica em toda seção e de fechamento, sem caminho de máquina e sem consultar o gerador nem a régua. Nenhum número das Notas é inventado: todos vêm da saída executada logo acima.

## Os notebooks

| notebook | o que responde |
|---|---|
| `01_sql_analitico` | as perguntas do `docs/01` respondidas com funções de janela: a série da filial (D1), o Pareto dos clientes (D2, A1), o aviso e o fim (D3), o mercado e o serviço com a defasagem medida (D4), o funil por trimestre (D5), o informado contra o apurado (D6), a coorte de 90 dias e os postos descobertos em sequência |

O SQL não mora no notebook: mora em `src/rh_fictalent/gold/analitico.py`, onde cada consulta declara a pergunta, a afirmação ou o indicador de origem e as janelas que usa (partição, ordem e quadro), e tem a semântica provada em teste num cenário pequeno (`tests/test_gold.py`). O notebook é a projeção dessas consultas sobre o dado inteiro, com a leitura ao lado. A mesma consulta roda pela linha de comando:

```bash
.venv/bin/python -m rh_fictalent.gold --analitico                      # lista as consultas
.venv/bin/python -m rh_fictalent.gold --analitico pareto_de_clientes   # roda uma sobre a gold publicada
```

## Como rodar

Com a plataforma de pé (`docker compose up -d`), a gold publicada (`python -m rh_fictalent.gold --publicar` ou o job `construir_gold`) e o `.env` preenchido, da raiz do projeto:

```bash
.venv/bin/python -m rh_fictalent.gold --notebook              # executa e verifica os notebooks desta pasta
```

A execução regrava o notebook com as saídas; é essa versão que vai para o repositório. A verificação do padrão é a mesma dos notebooks da auditoria (`rh_fictalent.auditoria.cadernos`) e roda na CI sem lake, pelos testes.

## O que não está aqui

A conclusão sobre as sete afirmações dos donos. Este notebook entrega os números e as séries; a análise, com o olhar de quem conhece o caso, é outro notebook, escrito pelo Tiago com apoio do Code, depois que a gold estiver no warehouse.

---

[Início](#topo)
