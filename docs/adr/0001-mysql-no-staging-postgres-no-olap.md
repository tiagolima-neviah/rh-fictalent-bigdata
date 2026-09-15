# ADR-0001 · MySQL na réplica do cliente (staging), Postgres no warehouse (OLAP)

**Situação:** aceito em 15/09/2026. Substitui a decisão registrada no `docs/03` da v0.1.0, que colocava Postgres na origem e no staging e MySQL no warehouse.

## Contexto

O projeto reproduz a situação real de uma consultoria de dados: o sistema produtivo do cliente é dele, e a consultoria **não o toca**. O que ela recebe é uma réplica autorizada, em ambiente apartado, e é dessa réplica que o pipeline lê. Dois motores de banco entram no projeto, o da réplica e o do warehouse, e era preciso decidir qual vai onde.

A primeira resposta (Postgres na réplica, MySQL no warehouse, "para o portfólio provar três bancos") não sobreviveu a duas perguntas: MySQL é banco analítico? E o que a série quer provar com ele?

## Decisão

- **Réplica (staging): MySQL 8.** A réplica espelha o motor do cliente, e MySQL é o motor mais provável do sistema próprio de uma PME de serviços fundada em 2018. O que o mercado pede é saber **ingerir de** MySQL, e isso só se prova extraindo dele: backfill e carga incremental saem daqui para a bronze, por marca d'água ou pelo binlog (a decidir e registrar na v0.5.0). Fecha a terceira técnica de carga incremental da série: Fictitur por coluna temporal, Fictoria por `rowversion`, Fictalent a partir de MySQL.
- **Warehouse (OLAP): Postgres 16.** É onde a API e as ferramentas de BI consultam. Postgres tem *row level security* nativa (o isolamento por filial vive aqui), visão materializada, execução paralela de consulta, schemas dentro do banco para separar `dim` e `fato`, e destino gratuito em nuvem já provado na série (Neon, na Fictitur).

## Alternativas consideradas

| alternativa | por que não |
|---|---|
| MySQL no warehouse e Postgres na réplica (a decisão original) | MySQL não é banco analítico: não tem RLS, não tem visão materializada, não executa consulta em paralelo e não tem schemas dentro de um banco (`dim` e `fato` virariam bancos separados). "Provar três bancos" não é necessidade do caso, é vitrine, e entrevistador sênior percebe. |
| Postgres nos dois | Não prova ingestão heterogênea nem a verossimilhança de uma réplica que espelha o motor do cliente. Seria a Fictitur de novo. |
| Um banco de "origem" separado da réplica, com replicação entre os dois dentro do projeto | A consultoria nunca teria acesso a esse banco: ele não existe no ambiente dela. Modelá-lo aqui seria simular uma camada que o trabalho real não tem. O gerador faz o papel do sistema do cliente e da replicação, escrevendo direto na réplica. |

## Consequências

- O MySQL sobe na fundação (v0.2.0), não na v0.7.0, e a DDL dos 10 módulos nasce em MySQL.
- Em MySQL, *schema* e *database* são a mesma coisa: os 10 módulos viram 10 databases na instância (`cadastro`, `comercial`, ...), e o DCL concede privilégios por database.
- O isolamento por filial (RLS) sai da réplica e vai para o warehouse, onde estão os leitores por área e por filial. A réplica fica com DCL por perfil e cifra em repouso do dado pessoal.
- A ingestão relacional lê MySQL via ADBC; a marca d'água por tabela fica do lado do pipeline, não dentro da réplica.
- A trilha de exclusões (`meta.exclusao_auditoria`) vive na réplica, por gatilho de `DELETE`.
- **Réplica parcial por pertinência** é a regra da casa: replica-se só o que a dor contratada exige, com mapa de escopo documentado (`docs/03`, seção 3). Neste caso a réplica é completa por autorização do cliente, e o mapa existe do mesmo jeito.
- A Fictitur não muda: segue em Postgres. O retrofit dos projetos anteriores é trilha de aprendizado, fora deste repositório.
