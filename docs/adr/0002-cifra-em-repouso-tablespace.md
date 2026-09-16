# ADR-0002 · Cifra em repouso por tablespace do InnoDB com keyring próprio, não por coluna

**Situação:** aceito em 16/09/2026.

## Contexto

A réplica guarda dado pessoal (CPF, nome, nascimento, PIS, endereço) e dado pessoal sensível (saúde: CID do afastamento, resultado do ASO, acidente). A LGPD pede proteção em repouso, e o caso pede uma resposta honesta a "protegido contra o quê". Três ameaças diferentes pedem três controles diferentes: alguém que **lê o disco** (volume copiado, backup extraviado, `.ibd` lido fora do servidor), alguém que **consulta o banco** com um usuário que tem `SELECT`, e alguém que **lê a camada analítica** (lake e warehouse). Este ADR decide o primeiro controle; o DCL por função (`docs/04`, seção 7) responde ao segundo e a pseudonimização na silver ao terceiro.

## Decisão

Cifrar **a réplica inteira** com a cifra de tablespace do InnoDB: `ENCRYPTION='Y'` em cada uma das 76 tabelas e `DEFAULT ENCRYPTION='Y'` em cada database, declarados na própria DDL; `default_table_encryption=ON` e `table_encryption_privilege_check=ON` no servidor, de modo que só `TABLE_ENCRYPTION_ADMIN` cria tabela em claro; redo log, undo log e binlog cifrados também, porque o dado passa por eles antes do tablespace. A chave mestra fica no `component_keyring_file`, carregado por manifesto, gravada num volume próprio (`mysql_keyring`) fora do repositório e fora do diretório de dados, rotacionável com `ALTER INSTANCE ROTATE INNODB MASTER KEY`. O container da réplica roda como o usuário `mysql` (999) desde o início, sem root, o que é o que faz a chave nascer com o dono certo.

## Alternativas consideradas

| alternativa | por que não |
|---|---|
| **Cifra de coluna** (`AES_ENCRYPT` no CPF e nas demais colunas etiquetadas) | A chave teria de estar em todo consumidor que lê a coluna (pipeline, relatórios, gerador), o que multiplica os lugares onde ela pode vazar; o índice único do CPF em `pessoas.colaborador` deixa de existir sobre o texto cifrado; a proteção contra usuário de banco, que é o argumento a favor, já é dada pelo DCL de coluna, que é o lugar dela. Sobra custo sem sobrar proteção nova. |
| **Cifra na aplicação** (o gerador cifra antes de gravar) | Igual à anterior nos custos, e ainda cega o próprio banco para validar o dado (`CHECK`, `UNIQUE`). |
| **Só cifra do volume** (disco do host, LUKS ou equivalente) | Protege o disco físico, não o volume Docker copiado nem um dump; é complementar, não substituto, e fica fora do que o repositório consegue demonstrar. |
| **Não cifrar** (só DCL e pseudonimização) | Deixa o backup e o volume como ponto único de exposição do dado pessoal inteiro, e é exatamente o cenário de vazamento mais comum. |

## O custo, medido

`bash scripts/medir_cifra.sh` cria duas tabelas iguais em `cadastro`, uma com `ENCRYPTION='N'` e outra com `ENCRYPTION='Y'`, escreve 200 mil linhas (CPF de 11 dígitos e um texto de 150 caracteres) em cada uma, lê tudo e compara. Duas rodadas em 16/09/2026, nesta estação, MySQL 8.4.11 em container:

| | em claro | cifrada | diferença |
|---|---|---|---|
| escrita de 200 mil linhas (rodada 1 / rodada 2) | 852 ms / 807 ms | 875 ms / 869 ms | +3% a +8% |
| leitura completa, 200 mil linhas e 30 MB de texto (rodada 1 / rodada 2) | 109 ms / 140 ms | 139 ms / 100 ms | dentro do ruído (±40 ms entre rodadas, para os dois lados) |
| tamanho em disco | 49.156 KB | 49.156 KB | nenhuma |

A escrita paga um custo pequeno e consistente; a leitura não mostrou diferença que sobreviva a duas rodadas (a segunda leu a tabela cifrada mais rápido que a em claro, efeito de cache do buffer pool). Para o volume deste caso (cerca de 8 milhões de linhas no total, carga diária incremental), o custo é irrelevante; a cifra não muda o tamanho porque cifra página a página, sem alterar o layout.

## Consequências

- A prova de que o dado não está em claro no disco é um teste (`tests/test_cifra_aplicada.py`): um CPF gravado em `pessoas.colaborador` não é encontrado no `.ibd` cifrado e é encontrado numa tabela de controle criada em claro.
- **Sem o keyring, o dado é irrecuperável.** Backup da réplica inclui o volume da chave; o manual de backup (v1.0.0) trata os dois juntos. `docker compose down -v` apaga chave e dados ao mesmo tempo, de propósito.
- O `component_keyring_file` é a opção de laboratório: em produção a chave iria para um KMS ou HSM (componentes de keyring do MySQL Enterprise ou da nuvem); o desenho (manifesto + componente) é o mesmo, só troca o backend. Isto é um dos motivos pelos quais o aviso de "não usar em produção" do README continua valendo.
- Um volume criado antes da cifra é convertido por `staging/ddl/15_cifra.sql`, gerado da DDL; um volume novo já nasce cifrado.
