# ADR-0011 · Marca d'água por `atualizado_em`, não CDC por binlog

**Situação:** aceito em 22/09/2026. Entra na v0.5.0.

## Contexto

A réplica tem 8,4 milhões de linhas e muda todo dia. Rodar o backfill diariamente custaria 124 segundos e transferiria a base inteira para reescrever o que já estava igual. A carga incremental precisa saber **o que mudou desde a última vez**, e há duas famílias de resposta: perguntar ao dado (uma coluna de carimbo que a origem mantém) ou escutar o log de replicação do banco (CDC, *change data capture*).

Duas restrições do caso decidem mais do que a preferência técnica. A primeira: **a réplica é do cliente**. O pipeline lê, não escreve, nem para anotar o próprio progresso, e não configura o servidor dela. A segunda: o projeto é de estudo e precisa ser reproduzível numa máquina limpa, com `docker compose up`, sem passo manual de infraestrutura.

## Decisão

**Marca d'água por `atualizado_em`.** Toda tabela de negócio da réplica tem `criado_em` e `atualizado_em` mantidos pelo próprio MySQL (`ON UPDATE CURRENT_TIMESTAMP(6)`) e indexados desde a DDL da v0.2.0. A carga pede as linhas acima da marca, aplica por id nas partições que o ano de `criado_em` indica, e confere a contagem de cada partição tocada.

A marca fica **no warehouse** (`ingestao.marca_dagua`), ao lado das métricas de execução: é estado do pipeline, não do cliente. Ela é um instante do **relógio da réplica**, pedido a ela (`SELECT NOW(6)`), porque é esse relógio que grava `atualizado_em`.

Três cuidados entram junto, e cada um existe por uma falha concreta:

- **Sobreposição de uma hora.** `atualizado_em` é gravado quando o `UPDATE` roda, mas a linha só fica visível no commit. Uma transação que grava 10:00:00 e commita 10:00:05 é invisível para a carga das 10:00:02 e ficaria abaixo da marca nova para sempre. A carga volta um pouco no tempo; reler é inofensivo porque a aplicação é por id.
- **Foto renovada a cada tabela.** Em REPEATABLE READ, que é o padrão do InnoDB, a transação que o driver abre na primeira leitura congela o que a conexão enxerga. Sem descartá-la, a segunda carga na mesma conexão leria o mundo da primeira. Isso não é hipótese: foi o primeiro resultado da primeira prova contra a réplica.
- **Exclusão não é problema da marca.** `DELETE` não deixa `atualizado_em` para ser encontrado. A conferência de contagem por partição detecta o buraco, e quem o explica é a trilha de `meta.exclusao_auditoria` (gatilhos da v0.2.0): a linha apagada **ganha `excluido_em` na bronze em vez de sumir**, e a conferência passa a contar as vivas (card 5.3).

## Alternativas consideradas

| alternativa | por que não |
|---|---|
| CDC por binlog (Debezium, Maxwell, `python-mysql-replication`) | é a resposta certa para latência de segundos e captura de `DELETE` sem trilha, mas exige `log_bin` em formato de linha, um usuário com `REPLICATION SLAVE` e um processo a mais de pé (Debezium pede Kafka ou Connect). Configurar o servidor do cliente não é do escopo da consultoria, e o custo de operar não paga para uma carga diária |
| Gatilho de auditoria em toda tabela, como fila de mudanças | dobraria a escrita na réplica do cliente para servir ao pipeline; a trilha de `DELETE` já existe porque exclusão não tem outra saída, e ela é a exceção justificada, não a regra |
| Comparar a bronze com a réplica por hash, sem carimbo | ler as duas pontas inteiras todo dia é o backfill com passos a mais |
| Marca guardada na própria réplica | escrever no banco do cliente para anotar o progresso do pipeline, o que o desenho da v0.2.0 proíbe (o usuário `pipeline` é só leitura) |
| Marca guardada no lake, num arquivo de controle | funciona, mas um JSON em S3 não é transacional e não se consulta por SQL; o Grafana já lê o warehouse |

## Consequências

- A latência é a da agenda, não do banco: a carga roda às 5h e o dado do dia anterior está na bronze de manhã. Latência de segundos precisaria de CDC, e isso está fora do caso.
- A carga depende de `atualizado_em` ser fiel. O motor o mantém, mas um `UPDATE` que o fixe à mão (o gerador faz isso de propósito, para restaurar estado) passa despercebido. A conferência de contagem não pega isso, porque o número de linhas não muda; quem pega é `refazer`, a recópia da tabela inteira.
- A escolha é reversível. Se um dia o caso exigir CDC, a bronze não muda de forma: continua parquet particionado por ano, e o que muda é quem descobre a alteração.
- Medido na v0.5.0: carga diária sem nada a fazer em **845 ms**; com a marca derivada da bronze pela primeira vez, 22 segundos para as 75 tabelas.
