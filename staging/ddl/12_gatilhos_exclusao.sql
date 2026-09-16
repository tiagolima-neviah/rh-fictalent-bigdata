-- Trilha de exclusões · um gatilho BEFORE DELETE por tabela de negócio.
--
-- ARQUIVO GERADO por src/rh_fictalent/staging/gatilhos.py a partir da DDL dos módulos.
-- Não edite à mão: rode  python -m rh_fictalent.staging.gatilhos  e versione o resultado.
--
-- Cada gatilho grava em meta.exclusao_auditoria o database, a tabela, o id e o usuário de
-- banco, antes de a linha sumir. Corre na mesma transação do DELETE: uma exclusão barrada
-- por chave estrangeira é desfeita junto com o rastro. meta não tem gatilho (só insere).

-- cadastro (12 tabelas)
CREATE TRIGGER IF NOT EXISTS cadastro.trg_regiao_exclusao
  BEFORE DELETE ON cadastro.regiao FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('cadastro', 'regiao', OLD.id, CURRENT_USER());
CREATE TRIGGER IF NOT EXISTS cadastro.trg_municipio_exclusao
  BEFORE DELETE ON cadastro.municipio FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('cadastro', 'municipio', OLD.id, CURRENT_USER());
CREATE TRIGGER IF NOT EXISTS cadastro.trg_endereco_exclusao
  BEFORE DELETE ON cadastro.endereco FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('cadastro', 'endereco', OLD.id, CURRENT_USER());
CREATE TRIGGER IF NOT EXISTS cadastro.trg_filial_exclusao
  BEFORE DELETE ON cadastro.filial FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('cadastro', 'filial', OLD.id, CURRENT_USER());
CREATE TRIGGER IF NOT EXISTS cadastro.trg_motivo_exclusao
  BEFORE DELETE ON cadastro.motivo FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('cadastro', 'motivo', OLD.id, CURRENT_USER());
CREATE TRIGGER IF NOT EXISTS cadastro.trg_funcao_exclusao
  BEFORE DELETE ON cadastro.funcao FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('cadastro', 'funcao', OLD.id, CURRENT_USER());
CREATE TRIGGER IF NOT EXISTS cadastro.trg_convencao_coletiva_exclusao
  BEFORE DELETE ON cadastro.convencao_coletiva FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('cadastro', 'convencao_coletiva', OLD.id, CURRENT_USER());
CREATE TRIGGER IF NOT EXISTS cadastro.trg_piso_salarial_exclusao
  BEFORE DELETE ON cadastro.piso_salarial FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('cadastro', 'piso_salarial', OLD.id, CURRENT_USER());
CREATE TRIGGER IF NOT EXISTS cadastro.trg_feriado_exclusao
  BEFORE DELETE ON cadastro.feriado FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('cadastro', 'feriado', OLD.id, CURRENT_USER());
CREATE TRIGGER IF NOT EXISTS cadastro.trg_escala_exclusao
  BEFORE DELETE ON cadastro.escala FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('cadastro', 'escala', OLD.id, CURRENT_USER());
CREATE TRIGGER IF NOT EXISTS cadastro.trg_parametro_exclusao
  BEFORE DELETE ON cadastro.parametro FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('cadastro', 'parametro', OLD.id, CURRENT_USER());
CREATE TRIGGER IF NOT EXISTS cadastro.trg_centro_custo_exclusao
  BEFORE DELETE ON cadastro.centro_custo FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('cadastro', 'centro_custo', OLD.id, CURRENT_USER());

-- comercial (8 tabelas)
CREATE TRIGGER IF NOT EXISTS comercial.trg_cliente_exclusao
  BEFORE DELETE ON comercial.cliente FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('comercial', 'cliente', OLD.id, CURRENT_USER());
CREATE TRIGGER IF NOT EXISTS comercial.trg_cliente_contato_exclusao
  BEFORE DELETE ON comercial.cliente_contato FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('comercial', 'cliente_contato', OLD.id, CURRENT_USER());
CREATE TRIGGER IF NOT EXISTS comercial.trg_contrato_exclusao
  BEFORE DELETE ON comercial.contrato FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('comercial', 'contrato', OLD.id, CURRENT_USER());
CREATE TRIGGER IF NOT EXISTS comercial.trg_contrato_aditivo_exclusao
  BEFORE DELETE ON comercial.contrato_aditivo FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('comercial', 'contrato_aditivo', OLD.id, CURRENT_USER());
CREATE TRIGGER IF NOT EXISTS comercial.trg_posto_exclusao
  BEFORE DELETE ON comercial.posto FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('comercial', 'posto', OLD.id, CURRENT_USER());
CREATE TRIGGER IF NOT EXISTS comercial.trg_posto_preco_exclusao
  BEFORE DELETE ON comercial.posto_preco FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('comercial', 'posto_preco', OLD.id, CURRENT_USER());
CREATE TRIGGER IF NOT EXISTS comercial.trg_sla_contrato_exclusao
  BEFORE DELETE ON comercial.sla_contrato FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('comercial', 'sla_contrato', OLD.id, CURRENT_USER());
CREATE TRIGGER IF NOT EXISTS comercial.trg_contrato_ocorrencia_exclusao
  BEFORE DELETE ON comercial.contrato_ocorrencia FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('comercial', 'contrato_ocorrencia', OLD.id, CURRENT_USER());

-- ats (9 tabelas)
CREATE TRIGGER IF NOT EXISTS ats.trg_fonte_candidato_exclusao
  BEFORE DELETE ON ats.fonte_candidato FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('ats', 'fonte_candidato', OLD.id, CURRENT_USER());
CREATE TRIGGER IF NOT EXISTS ats.trg_etapa_funil_exclusao
  BEFORE DELETE ON ats.etapa_funil FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('ats', 'etapa_funil', OLD.id, CURRENT_USER());
CREATE TRIGGER IF NOT EXISTS ats.trg_requisicao_exclusao
  BEFORE DELETE ON ats.requisicao FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('ats', 'requisicao', OLD.id, CURRENT_USER());
CREATE TRIGGER IF NOT EXISTS ats.trg_vaga_exclusao
  BEFORE DELETE ON ats.vaga FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('ats', 'vaga', OLD.id, CURRENT_USER());
CREATE TRIGGER IF NOT EXISTS ats.trg_candidato_exclusao
  BEFORE DELETE ON ats.candidato FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('ats', 'candidato', OLD.id, CURRENT_USER());
CREATE TRIGGER IF NOT EXISTS ats.trg_candidato_experiencia_exclusao
  BEFORE DELETE ON ats.candidato_experiencia FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('ats', 'candidato_experiencia', OLD.id, CURRENT_USER());
CREATE TRIGGER IF NOT EXISTS ats.trg_candidatura_exclusao
  BEFORE DELETE ON ats.candidatura FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('ats', 'candidatura', OLD.id, CURRENT_USER());
CREATE TRIGGER IF NOT EXISTS ats.trg_candidatura_etapa_exclusao
  BEFORE DELETE ON ats.candidatura_etapa FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('ats', 'candidatura_etapa', OLD.id, CURRENT_USER());
CREATE TRIGGER IF NOT EXISTS ats.trg_entrevista_exclusao
  BEFORE DELETE ON ats.entrevista FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('ats', 'entrevista', OLD.id, CURRENT_USER());

-- pessoas (8 tabelas)
CREATE TRIGGER IF NOT EXISTS pessoas.trg_colaborador_exclusao
  BEFORE DELETE ON pessoas.colaborador FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('pessoas', 'colaborador', OLD.id, CURRENT_USER());
CREATE TRIGGER IF NOT EXISTS pessoas.trg_colaborador_documento_exclusao
  BEFORE DELETE ON pessoas.colaborador_documento FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('pessoas', 'colaborador_documento', OLD.id, CURRENT_USER());
CREATE TRIGGER IF NOT EXISTS pessoas.trg_dependente_exclusao
  BEFORE DELETE ON pessoas.dependente FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('pessoas', 'dependente', OLD.id, CURRENT_USER());
CREATE TRIGGER IF NOT EXISTS pessoas.trg_contrato_trabalho_exclusao
  BEFORE DELETE ON pessoas.contrato_trabalho FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('pessoas', 'contrato_trabalho', OLD.id, CURRENT_USER());
CREATE TRIGGER IF NOT EXISTS pessoas.trg_contrato_trabalho_prorrogacao_exclusao
  BEFORE DELETE ON pessoas.contrato_trabalho_prorrogacao FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('pessoas', 'contrato_trabalho_prorrogacao', OLD.id, CURRENT_USER());
CREATE TRIGGER IF NOT EXISTS pessoas.trg_alocacao_exclusao
  BEFORE DELETE ON pessoas.alocacao FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('pessoas', 'alocacao', OLD.id, CURRENT_USER());
CREATE TRIGGER IF NOT EXISTS pessoas.trg_afastamento_exclusao
  BEFORE DELETE ON pessoas.afastamento FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('pessoas', 'afastamento', OLD.id, CURRENT_USER());
CREATE TRIGGER IF NOT EXISTS pessoas.trg_desligamento_exclusao
  BEFORE DELETE ON pessoas.desligamento FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('pessoas', 'desligamento', OLD.id, CURRENT_USER());

-- ponto (5 tabelas)
CREATE TRIGGER IF NOT EXISTS ponto.trg_escala_colaborador_exclusao
  BEFORE DELETE ON ponto.escala_colaborador FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('ponto', 'escala_colaborador', OLD.id, CURRENT_USER());
CREATE TRIGGER IF NOT EXISTS ponto.trg_marcacao_exclusao
  BEFORE DELETE ON ponto.marcacao FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('ponto', 'marcacao', OLD.id, CURRENT_USER());
CREATE TRIGGER IF NOT EXISTS ponto.trg_apontamento_exclusao
  BEFORE DELETE ON ponto.apontamento FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('ponto', 'apontamento', OLD.id, CURRENT_USER());
CREATE TRIGGER IF NOT EXISTS ponto.trg_ocorrencia_ponto_exclusao
  BEFORE DELETE ON ponto.ocorrencia_ponto FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('ponto', 'ocorrencia_ponto', OLD.id, CURRENT_USER());
CREATE TRIGGER IF NOT EXISTS ponto.trg_banco_horas_exclusao
  BEFORE DELETE ON ponto.banco_horas FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('ponto', 'banco_horas', OLD.id, CURRENT_USER());

-- folha (7 tabelas)
CREATE TRIGGER IF NOT EXISTS folha.trg_evento_folha_exclusao
  BEFORE DELETE ON folha.evento_folha FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('folha', 'evento_folha', OLD.id, CURRENT_USER());
CREATE TRIGGER IF NOT EXISTS folha.trg_beneficio_exclusao
  BEFORE DELETE ON folha.beneficio FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('folha', 'beneficio', OLD.id, CURRENT_USER());
CREATE TRIGGER IF NOT EXISTS folha.trg_folha_competencia_exclusao
  BEFORE DELETE ON folha.folha_competencia FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('folha', 'folha_competencia', OLD.id, CURRENT_USER());
CREATE TRIGGER IF NOT EXISTS folha.trg_folha_item_exclusao
  BEFORE DELETE ON folha.folha_item FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('folha', 'folha_item', OLD.id, CURRENT_USER());
CREATE TRIGGER IF NOT EXISTS folha.trg_provisao_exclusao
  BEFORE DELETE ON folha.provisao FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('folha', 'provisao', OLD.id, CURRENT_USER());
CREATE TRIGGER IF NOT EXISTS folha.trg_colaborador_beneficio_exclusao
  BEFORE DELETE ON folha.colaborador_beneficio FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('folha', 'colaborador_beneficio', OLD.id, CURRENT_USER());
CREATE TRIGGER IF NOT EXISTS folha.trg_rateio_custo_exclusao
  BEFORE DELETE ON folha.rateio_custo FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('folha', 'rateio_custo', OLD.id, CURRENT_USER());

-- financeiro (10 tabelas)
CREATE TRIGGER IF NOT EXISTS financeiro.trg_regime_tributario_exclusao
  BEFORE DELETE ON financeiro.regime_tributario FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('financeiro', 'regime_tributario', OLD.id, CURRENT_USER());
CREATE TRIGGER IF NOT EXISTS financeiro.trg_tributo_exclusao
  BEFORE DELETE ON financeiro.tributo FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('financeiro', 'tributo', OLD.id, CURRENT_USER());
CREATE TRIGGER IF NOT EXISTS financeiro.trg_aliquota_exclusao
  BEFORE DELETE ON financeiro.aliquota FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('financeiro', 'aliquota', OLD.id, CURRENT_USER());
CREATE TRIGGER IF NOT EXISTS financeiro.trg_fornecedor_exclusao
  BEFORE DELETE ON financeiro.fornecedor FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('financeiro', 'fornecedor', OLD.id, CURRENT_USER());
CREATE TRIGGER IF NOT EXISTS financeiro.trg_fatura_exclusao
  BEFORE DELETE ON financeiro.fatura FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('financeiro', 'fatura', OLD.id, CURRENT_USER());
CREATE TRIGGER IF NOT EXISTS financeiro.trg_fatura_item_exclusao
  BEFORE DELETE ON financeiro.fatura_item FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('financeiro', 'fatura_item', OLD.id, CURRENT_USER());
CREATE TRIGGER IF NOT EXISTS financeiro.trg_titulo_receber_exclusao
  BEFORE DELETE ON financeiro.titulo_receber FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('financeiro', 'titulo_receber', OLD.id, CURRENT_USER());
CREATE TRIGGER IF NOT EXISTS financeiro.trg_titulo_pagar_exclusao
  BEFORE DELETE ON financeiro.titulo_pagar FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('financeiro', 'titulo_pagar', OLD.id, CURRENT_USER());
CREATE TRIGGER IF NOT EXISTS financeiro.trg_imposto_apurado_exclusao
  BEFORE DELETE ON financeiro.imposto_apurado FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('financeiro', 'imposto_apurado', OLD.id, CURRENT_USER());
CREATE TRIGGER IF NOT EXISTS financeiro.trg_consolidado_gerencial_exclusao
  BEFORE DELETE ON financeiro.consolidado_gerencial FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('financeiro', 'consolidado_gerencial', OLD.id, CURRENT_USER());

-- treinamento (5 tabelas)
CREATE TRIGGER IF NOT EXISTS treinamento.trg_curso_exclusao
  BEFORE DELETE ON treinamento.curso FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('treinamento', 'curso', OLD.id, CURRENT_USER());
CREATE TRIGGER IF NOT EXISTS treinamento.trg_curso_funcao_exclusao
  BEFORE DELETE ON treinamento.curso_funcao FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('treinamento', 'curso_funcao', OLD.id, CURRENT_USER());
CREATE TRIGGER IF NOT EXISTS treinamento.trg_turma_exclusao
  BEFORE DELETE ON treinamento.turma FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('treinamento', 'turma', OLD.id, CURRENT_USER());
CREATE TRIGGER IF NOT EXISTS treinamento.trg_turma_participante_exclusao
  BEFORE DELETE ON treinamento.turma_participante FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('treinamento', 'turma_participante', OLD.id, CURRENT_USER());
CREATE TRIGGER IF NOT EXISTS treinamento.trg_certificado_exclusao
  BEFORE DELETE ON treinamento.certificado FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('treinamento', 'certificado', OLD.id, CURRENT_USER());

-- sst (6 tabelas)
CREATE TRIGGER IF NOT EXISTS sst.trg_tipo_exame_exclusao
  BEFORE DELETE ON sst.tipo_exame FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('sst', 'tipo_exame', OLD.id, CURRENT_USER());
CREATE TRIGGER IF NOT EXISTS sst.trg_aso_exclusao
  BEFORE DELETE ON sst.aso FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('sst', 'aso', OLD.id, CURRENT_USER());
CREATE TRIGGER IF NOT EXISTS sst.trg_programa_sst_exclusao
  BEFORE DELETE ON sst.programa_sst FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('sst', 'programa_sst', OLD.id, CURRENT_USER());
CREATE TRIGGER IF NOT EXISTS sst.trg_risco_posto_exclusao
  BEFORE DELETE ON sst.risco_posto FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('sst', 'risco_posto', OLD.id, CURRENT_USER());
CREATE TRIGGER IF NOT EXISTS sst.trg_acidente_exclusao
  BEFORE DELETE ON sst.acidente FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('sst', 'acidente', OLD.id, CURRENT_USER());
CREATE TRIGGER IF NOT EXISTS sst.trg_cat_exclusao
  BEFORE DELETE ON sst.cat FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('sst', 'cat', OLD.id, CURRENT_USER());

-- seguranca (5 tabelas)
CREATE TRIGGER IF NOT EXISTS seguranca.trg_perfil_exclusao
  BEFORE DELETE ON seguranca.perfil FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('seguranca', 'perfil', OLD.id, CURRENT_USER());
CREATE TRIGGER IF NOT EXISTS seguranca.trg_usuario_exclusao
  BEFORE DELETE ON seguranca.usuario FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('seguranca', 'usuario', OLD.id, CURRENT_USER());
CREATE TRIGGER IF NOT EXISTS seguranca.trg_usuario_perfil_exclusao
  BEFORE DELETE ON seguranca.usuario_perfil FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('seguranca', 'usuario_perfil', OLD.id, CURRENT_USER());
CREATE TRIGGER IF NOT EXISTS seguranca.trg_permissao_exclusao
  BEFORE DELETE ON seguranca.permissao FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('seguranca', 'permissao', OLD.id, CURRENT_USER());
CREATE TRIGGER IF NOT EXISTS seguranca.trg_log_auditoria_exclusao
  BEFORE DELETE ON seguranca.log_auditoria FOR EACH ROW
  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)
  VALUES ('seguranca', 'log_auditoria', OLD.id, CURRENT_USER());
