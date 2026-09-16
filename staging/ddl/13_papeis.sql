-- Papéis da réplica · o que cada função pode fazer, derivado da DDL.
--
-- ARQUIVO GERADO por src/rh_fictalent/staging/papeis.py.
-- Não edite à mão: rode  python -m rh_fictalent.staging.papeis  e versione o resultado.
--
--   papel_pipeline    só leitura em tudo, inclusive meta
--   papel_relatorios  leitura sem dado pessoal (coluna a coluna onde há etiqueta LGPD)
--   papel_replicador  escreve o negócio; nunca meta, nunca DDL, nunca GRANT
--
-- Os usuários que recebem estes papéis (com senha do .env) vêm de 14_usuarios.sh.
-- GRANT é idempotente: repetir não muda nada.

CREATE ROLE IF NOT EXISTS papel_pipeline, papel_relatorios, papel_replicador;

-- pipeline: só leitura, inclusive a trilha de exclusões
GRANT SELECT ON cadastro.* TO papel_pipeline;
GRANT SELECT ON comercial.* TO papel_pipeline;
GRANT SELECT ON ats.* TO papel_pipeline;
GRANT SELECT ON pessoas.* TO papel_pipeline;
GRANT SELECT ON ponto.* TO papel_pipeline;
GRANT SELECT ON folha.* TO papel_pipeline;
GRANT SELECT ON financeiro.* TO papel_pipeline;
GRANT SELECT ON treinamento.* TO papel_pipeline;
GRANT SELECT ON sst.* TO papel_pipeline;
GRANT SELECT ON seguranca.* TO papel_pipeline;
GRANT SELECT ON meta.* TO papel_pipeline;

-- replicador: escreve o negócio; meta fica de fora (o gatilho grava lá por conta própria)
GRANT SELECT, INSERT, UPDATE, DELETE ON cadastro.* TO papel_replicador;
GRANT SELECT, INSERT, UPDATE, DELETE ON comercial.* TO papel_replicador;
GRANT SELECT, INSERT, UPDATE, DELETE ON ats.* TO papel_replicador;
GRANT SELECT, INSERT, UPDATE, DELETE ON pessoas.* TO papel_replicador;
GRANT SELECT, INSERT, UPDATE, DELETE ON ponto.* TO papel_replicador;
GRANT SELECT, INSERT, UPDATE, DELETE ON folha.* TO papel_replicador;
GRANT SELECT, INSERT, UPDATE, DELETE ON financeiro.* TO papel_replicador;
GRANT SELECT, INSERT, UPDATE, DELETE ON treinamento.* TO papel_replicador;
GRANT SELECT, INSERT, UPDATE, DELETE ON sst.* TO papel_replicador;
GRANT SELECT, INSERT, UPDATE, DELETE ON seguranca.* TO papel_replicador;

-- relatórios do cliente: leitura sem dado pessoal

-- cadastro
GRANT SELECT ON cadastro.regiao TO papel_relatorios;
GRANT SELECT ON cadastro.municipio TO papel_relatorios;
GRANT SELECT (id, numero, complemento, bairro, municipio_id, tipo, criado_em, atualizado_em) ON cadastro.endereco TO papel_relatorios;  -- fora: logradouro, cep
GRANT SELECT ON cadastro.filial TO papel_relatorios;
GRANT SELECT ON cadastro.motivo TO papel_relatorios;
GRANT SELECT ON cadastro.funcao TO papel_relatorios;
GRANT SELECT ON cadastro.convencao_coletiva TO papel_relatorios;
GRANT SELECT ON cadastro.piso_salarial TO papel_relatorios;
GRANT SELECT ON cadastro.feriado TO papel_relatorios;
GRANT SELECT ON cadastro.escala TO papel_relatorios;
GRANT SELECT ON cadastro.parametro TO papel_relatorios;
GRANT SELECT ON cadastro.centro_custo TO papel_relatorios;

-- comercial
GRANT SELECT ON comercial.cliente TO papel_relatorios;
GRANT SELECT (id, cliente_id, cargo, fl_principal, criado_em, atualizado_em) ON comercial.cliente_contato TO papel_relatorios;  -- fora: nome, email, telefone
GRANT SELECT ON comercial.contrato TO papel_relatorios;
GRANT SELECT ON comercial.contrato_aditivo TO papel_relatorios;
GRANT SELECT ON comercial.posto TO papel_relatorios;
GRANT SELECT ON comercial.posto_preco TO papel_relatorios;
GRANT SELECT ON comercial.sla_contrato TO papel_relatorios;
GRANT SELECT ON comercial.contrato_ocorrencia TO papel_relatorios;

-- ats
GRANT SELECT ON ats.fonte_candidato TO papel_relatorios;
GRANT SELECT ON ats.etapa_funil TO papel_relatorios;
GRANT SELECT ON ats.requisicao TO papel_relatorios;
GRANT SELECT ON ats.vaga TO papel_relatorios;
GRANT SELECT (id, municipio_id, escolaridade, fonte_id, dt_cadastro, criado_em, atualizado_em) ON ats.candidato TO papel_relatorios;  -- fora: nome, cpf, dt_nascimento, sexo, telefone, email
GRANT SELECT ON ats.candidato_experiencia TO papel_relatorios;
GRANT SELECT ON ats.candidatura TO papel_relatorios;
GRANT SELECT ON ats.candidatura_etapa TO papel_relatorios;
GRANT SELECT ON ats.entrevista TO papel_relatorios;

-- pessoas
GRANT SELECT (id, candidato_id, matricula, municipio_id, dt_admissao_primeira, ativo, criado_em, atualizado_em) ON pessoas.colaborador TO papel_relatorios;  -- fora: nome, cpf, dt_nascimento, endereco_id, pis
GRANT SELECT (id, colaborador_id, tipo, orgao, dt_emissao, criado_em, atualizado_em) ON pessoas.colaborador_documento TO papel_relatorios;  -- fora: numero
GRANT SELECT (id, colaborador_id, parentesco, criado_em, atualizado_em) ON pessoas.dependente TO papel_relatorios;  -- fora: nome, dt_nascimento
GRANT SELECT ON pessoas.contrato_trabalho TO papel_relatorios;
GRANT SELECT ON pessoas.contrato_trabalho_prorrogacao TO papel_relatorios;
GRANT SELECT ON pessoas.alocacao TO papel_relatorios;
GRANT SELECT (id, colaborador_id, tipo, dt_inicio, dt_fim, motivo_id, criado_em, atualizado_em) ON pessoas.afastamento TO papel_relatorios;  -- fora: cid_grupo
GRANT SELECT ON pessoas.desligamento TO papel_relatorios;

-- ponto
GRANT SELECT ON ponto.escala_colaborador TO papel_relatorios;
GRANT SELECT ON ponto.marcacao TO papel_relatorios;
GRANT SELECT ON ponto.apontamento TO papel_relatorios;
GRANT SELECT ON ponto.ocorrencia_ponto TO papel_relatorios;
GRANT SELECT ON ponto.banco_horas TO papel_relatorios;

-- folha
GRANT SELECT ON folha.evento_folha TO papel_relatorios;
GRANT SELECT ON folha.beneficio TO papel_relatorios;
GRANT SELECT ON folha.folha_competencia TO papel_relatorios;
GRANT SELECT (id, folha_competencia_id, colaborador_id, contrato_trabalho_id, evento_id, referencia, criado_em, atualizado_em) ON folha.folha_item TO papel_relatorios;  -- fora: valor
GRANT SELECT ON folha.provisao TO papel_relatorios;
GRANT SELECT ON folha.colaborador_beneficio TO papel_relatorios;
GRANT SELECT ON folha.rateio_custo TO papel_relatorios;

-- financeiro
GRANT SELECT ON financeiro.regime_tributario TO papel_relatorios;
GRANT SELECT ON financeiro.tributo TO papel_relatorios;
GRANT SELECT ON financeiro.aliquota TO papel_relatorios;
GRANT SELECT ON financeiro.fornecedor TO papel_relatorios;
GRANT SELECT ON financeiro.fatura TO papel_relatorios;
GRANT SELECT ON financeiro.fatura_item TO papel_relatorios;
GRANT SELECT ON financeiro.titulo_receber TO papel_relatorios;
GRANT SELECT ON financeiro.titulo_pagar TO papel_relatorios;
GRANT SELECT ON financeiro.imposto_apurado TO papel_relatorios;
GRANT SELECT ON financeiro.consolidado_gerencial TO papel_relatorios;

-- treinamento
GRANT SELECT ON treinamento.curso TO papel_relatorios;
GRANT SELECT ON treinamento.curso_funcao TO papel_relatorios;
GRANT SELECT ON treinamento.turma TO papel_relatorios;
GRANT SELECT ON treinamento.turma_participante TO papel_relatorios;
GRANT SELECT ON treinamento.certificado TO papel_relatorios;

-- sst
GRANT SELECT ON sst.tipo_exame TO papel_relatorios;
GRANT SELECT (id, colaborador_id, tipo_exame_id, dt_exame, dt_validade, medico_crm, fornecedor_id, criado_em, atualizado_em) ON sst.aso TO papel_relatorios;  -- fora: resultado
GRANT SELECT ON sst.programa_sst TO papel_relatorios;
GRANT SELECT ON sst.risco_posto TO papel_relatorios;
GRANT SELECT (id, colaborador_id, alocacao_id, dt_acidente, dias_afastamento, afastamento_id, criado_em, atualizado_em) ON sst.acidente TO papel_relatorios;  -- fora: tipo, gravidade
GRANT SELECT ON sst.cat TO papel_relatorios;

-- seguranca
GRANT SELECT ON seguranca.perfil TO papel_relatorios;
GRANT SELECT (id, login, colaborador_id, filial_id, ativo, dt_criacao, ultimo_acesso, criado_em, atualizado_em) ON seguranca.usuario TO papel_relatorios;  -- fora: nome, email
GRANT SELECT ON seguranca.usuario_perfil TO papel_relatorios;
GRANT SELECT ON seguranca.permissao TO papel_relatorios;
GRANT SELECT (id, usuario_id, dt_evento, modulo, tabela, registro_id, acao, criado_em, atualizado_em) ON seguranca.log_auditoria TO papel_relatorios;  -- fora: valor_anterior, valor_novo
