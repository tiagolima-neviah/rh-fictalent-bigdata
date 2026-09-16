-- Cifra em repouso · todo database e toda tabela da réplica com ENCRYPTION='Y'.
--
-- ARQUIVO GERADO por src/rh_fictalent/staging/cifra.py a partir da DDL dos módulos.
-- Não edite à mão: rode  python -m rh_fictalent.staging.cifra  e versione o resultado.
--
-- Serve ao volume que já existia antes da cifra (a DDL nova já nasce cifrada). Exige o
-- componente de keyring carregado (infra/mysql/mysqld.my) e reescreve cada tablespace;
-- numa réplica já cifrada é inofensivo. Detalhe: docs/04_modelo_dados_staging.md, seção 8.

-- databases: tabela nova nasce cifrada por padrão
ALTER DATABASE cadastro DEFAULT ENCRYPTION='Y';
ALTER DATABASE comercial DEFAULT ENCRYPTION='Y';
ALTER DATABASE ats DEFAULT ENCRYPTION='Y';
ALTER DATABASE pessoas DEFAULT ENCRYPTION='Y';
ALTER DATABASE ponto DEFAULT ENCRYPTION='Y';
ALTER DATABASE folha DEFAULT ENCRYPTION='Y';
ALTER DATABASE financeiro DEFAULT ENCRYPTION='Y';
ALTER DATABASE treinamento DEFAULT ENCRYPTION='Y';
ALTER DATABASE sst DEFAULT ENCRYPTION='Y';
ALTER DATABASE seguranca DEFAULT ENCRYPTION='Y';
ALTER DATABASE meta DEFAULT ENCRYPTION='Y';

-- cadastro
ALTER TABLE cadastro.regiao ENCRYPTION='Y';
ALTER TABLE cadastro.municipio ENCRYPTION='Y';
ALTER TABLE cadastro.endereco ENCRYPTION='Y';
ALTER TABLE cadastro.filial ENCRYPTION='Y';
ALTER TABLE cadastro.motivo ENCRYPTION='Y';
ALTER TABLE cadastro.funcao ENCRYPTION='Y';
ALTER TABLE cadastro.convencao_coletiva ENCRYPTION='Y';
ALTER TABLE cadastro.piso_salarial ENCRYPTION='Y';
ALTER TABLE cadastro.feriado ENCRYPTION='Y';
ALTER TABLE cadastro.escala ENCRYPTION='Y';
ALTER TABLE cadastro.parametro ENCRYPTION='Y';
ALTER TABLE cadastro.centro_custo ENCRYPTION='Y';

-- comercial
ALTER TABLE comercial.cliente ENCRYPTION='Y';
ALTER TABLE comercial.cliente_contato ENCRYPTION='Y';
ALTER TABLE comercial.contrato ENCRYPTION='Y';
ALTER TABLE comercial.contrato_aditivo ENCRYPTION='Y';
ALTER TABLE comercial.posto ENCRYPTION='Y';
ALTER TABLE comercial.posto_preco ENCRYPTION='Y';
ALTER TABLE comercial.sla_contrato ENCRYPTION='Y';
ALTER TABLE comercial.contrato_ocorrencia ENCRYPTION='Y';

-- ats
ALTER TABLE ats.fonte_candidato ENCRYPTION='Y';
ALTER TABLE ats.etapa_funil ENCRYPTION='Y';
ALTER TABLE ats.requisicao ENCRYPTION='Y';
ALTER TABLE ats.vaga ENCRYPTION='Y';
ALTER TABLE ats.candidato ENCRYPTION='Y';
ALTER TABLE ats.candidato_experiencia ENCRYPTION='Y';
ALTER TABLE ats.candidatura ENCRYPTION='Y';
ALTER TABLE ats.candidatura_etapa ENCRYPTION='Y';
ALTER TABLE ats.entrevista ENCRYPTION='Y';

-- pessoas
ALTER TABLE pessoas.colaborador ENCRYPTION='Y';
ALTER TABLE pessoas.colaborador_documento ENCRYPTION='Y';
ALTER TABLE pessoas.dependente ENCRYPTION='Y';
ALTER TABLE pessoas.contrato_trabalho ENCRYPTION='Y';
ALTER TABLE pessoas.contrato_trabalho_prorrogacao ENCRYPTION='Y';
ALTER TABLE pessoas.alocacao ENCRYPTION='Y';
ALTER TABLE pessoas.afastamento ENCRYPTION='Y';
ALTER TABLE pessoas.desligamento ENCRYPTION='Y';

-- ponto
ALTER TABLE ponto.escala_colaborador ENCRYPTION='Y';
ALTER TABLE ponto.marcacao ENCRYPTION='Y';
ALTER TABLE ponto.apontamento ENCRYPTION='Y';
ALTER TABLE ponto.ocorrencia_ponto ENCRYPTION='Y';
ALTER TABLE ponto.banco_horas ENCRYPTION='Y';

-- folha
ALTER TABLE folha.evento_folha ENCRYPTION='Y';
ALTER TABLE folha.beneficio ENCRYPTION='Y';
ALTER TABLE folha.folha_competencia ENCRYPTION='Y';
ALTER TABLE folha.folha_item ENCRYPTION='Y';
ALTER TABLE folha.provisao ENCRYPTION='Y';
ALTER TABLE folha.colaborador_beneficio ENCRYPTION='Y';
ALTER TABLE folha.rateio_custo ENCRYPTION='Y';

-- financeiro
ALTER TABLE financeiro.regime_tributario ENCRYPTION='Y';
ALTER TABLE financeiro.tributo ENCRYPTION='Y';
ALTER TABLE financeiro.aliquota ENCRYPTION='Y';
ALTER TABLE financeiro.fornecedor ENCRYPTION='Y';
ALTER TABLE financeiro.fatura ENCRYPTION='Y';
ALTER TABLE financeiro.fatura_item ENCRYPTION='Y';
ALTER TABLE financeiro.titulo_receber ENCRYPTION='Y';
ALTER TABLE financeiro.titulo_pagar ENCRYPTION='Y';
ALTER TABLE financeiro.imposto_apurado ENCRYPTION='Y';
ALTER TABLE financeiro.consolidado_gerencial ENCRYPTION='Y';

-- treinamento
ALTER TABLE treinamento.curso ENCRYPTION='Y';
ALTER TABLE treinamento.curso_funcao ENCRYPTION='Y';
ALTER TABLE treinamento.turma ENCRYPTION='Y';
ALTER TABLE treinamento.turma_participante ENCRYPTION='Y';
ALTER TABLE treinamento.certificado ENCRYPTION='Y';

-- sst
ALTER TABLE sst.tipo_exame ENCRYPTION='Y';
ALTER TABLE sst.aso ENCRYPTION='Y';
ALTER TABLE sst.programa_sst ENCRYPTION='Y';
ALTER TABLE sst.risco_posto ENCRYPTION='Y';
ALTER TABLE sst.acidente ENCRYPTION='Y';
ALTER TABLE sst.cat ENCRYPTION='Y';

-- seguranca
ALTER TABLE seguranca.perfil ENCRYPTION='Y';
ALTER TABLE seguranca.usuario ENCRYPTION='Y';
ALTER TABLE seguranca.usuario_perfil ENCRYPTION='Y';
ALTER TABLE seguranca.permissao ENCRYPTION='Y';
ALTER TABLE seguranca.log_auditoria ENCRYPTION='Y';

-- meta
ALTER TABLE meta.exclusao_auditoria ENCRYPTION='Y';
