-- Fictalent RH · réplica do sistema do cliente (MySQL 8)
--
-- Em MySQL, schema e database são a mesma coisa: cada módulo do sistema é um database
-- desta instância. Os arquivos seguintes criam as tabelas na ordem das dependências.
-- Tudo aqui é idempotente (IF NOT EXISTS): pode rodar na primeira inicialização do
-- container ou por cima de uma réplica já existente (scripts/aplicar_ddl.sh).
--
-- Convenções do banco inteiro (detalhe em docs/04_modelo_dados_staging.md):
--   id             BIGINT UNSIGNED AUTO_INCREMENT, chave primária de toda tabela
--   criado_em      DATETIME(6) em UTC, preenchido pelo motor
--   atualizado_em  DATETIME(6) em UTC, mantido pelo motor (ON UPDATE) e INDEXADO em
--                  toda tabela: é a marca d agua da carga incremental
--   vigencia_fim   NULL significa vigente
--   competencia    DATE no primeiro dia do mês
--   CHECK no lugar de ENUM; DECIMAL(14,2) para dinheiro; DECIMAL(7,4) para percentual
--   ENCRYPTION='Y' em toda tabela e DEFAULT ENCRYPTION='Y' em todo database: cifra em
--   repouso pelo InnoDB, chave mestra no keyring (fora do repositório e do diretório de dados)
--   comentário em toda tabela; colunas de dado pessoal etiquetadas [LGPD:pessoal] ou
--   [LGPD:sensivel] no próprio comentário, de onde o dicionário de dados é gerado;
--   tabela de referência de domínio público leva [LGPD:publica] no comentário de tabela

CREATE DATABASE IF NOT EXISTS cadastro    CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT ENCRYPTION='Y';
CREATE DATABASE IF NOT EXISTS comercial   CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT ENCRYPTION='Y';
CREATE DATABASE IF NOT EXISTS ats         CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT ENCRYPTION='Y';
CREATE DATABASE IF NOT EXISTS pessoas     CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT ENCRYPTION='Y';
CREATE DATABASE IF NOT EXISTS ponto       CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT ENCRYPTION='Y';
CREATE DATABASE IF NOT EXISTS folha       CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT ENCRYPTION='Y';
CREATE DATABASE IF NOT EXISTS financeiro  CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT ENCRYPTION='Y';
CREATE DATABASE IF NOT EXISTS treinamento CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT ENCRYPTION='Y';
CREATE DATABASE IF NOT EXISTS sst         CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT ENCRYPTION='Y';
CREATE DATABASE IF NOT EXISTS seguranca   CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT ENCRYPTION='Y';
CREATE DATABASE IF NOT EXISTS meta        CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT ENCRYPTION='Y';
