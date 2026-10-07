"""O contrato da API: cada campo com o que é, no português do negócio; a OpenAPI sai daqui.

Dinheiro sai como número JSON com duas casas (o JSON não tem decimal): a gold e o warehouse
guardam decimal do começo ao fim, e a API só serve; quem soma de novo do lado de lá o faz
sobre centavos já fechados.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Saude(BaseModel):
    situacao: str = Field(description="`ok` quando o warehouse responde; `degradada` quando não")
    warehouse: bool = Field(description="o warehouse respondeu a um SELECT 1")
    versao: str = Field(description="a versão do contrato")


class Filial(BaseModel):
    id: int
    codigo: str | None = None
    nome: str
    tipo: str | None = Field(default=None, description="MATRIZ ou FILIAL")
    municipio: str | None = None
    uf: str | None = None
    ativo: bool | None = None


class ResultadoDoMes(BaseModel):
    """Uma filial num mês: o que faturou, custou e sobrou (`fato.resultado_mes`)."""

    mes_id: int = Field(description="o mês como AAAAMM")
    mes_parcial: bool = Field(description="o mês do horizonte: ainda sem fatura, não compare")
    faturamento: float = Field(description="receita bruta faturada no mês")
    faturamento_liquido: float = Field(description="receita menos os impostos sobre a fatura")
    custo_pessoal: float = Field(description="o custo das pessoas rateado aos postos da filial")
    impostos: float = Field(description="ISS da filial mais o federal rateado")
    despesas: float = Field(description="a despesa da retaguarda rateada pelo faturamento")
    resultado: float = Field(description="faturamento menos custo, impostos e despesas")
    margem_liquida: float | None = Field(
        description="resultado sobre o faturamento; nulo sem faturamento"
    )
    pessoas_alocadas: int | None = Field(description="pessoas alocadas no fim do mês")
    clientes_ativos: int | None = Field(description="clientes com contrato vigente no fim do mês")
    vagas_abertas: int | None = Field(description="vagas abertas no fim do mês")


class ClienteDoAno(BaseModel):
    """Um cliente no Pareto da receita do ano (`fato.posto_mes` por cliente)."""

    cliente_id: int
    cliente: str = Field(description="o nome fantasia")
    porte: str | None = None
    receita: float = Field(description="a receita dos postos do cliente no ano")
    margem: float = Field(description="receita menos o custo de pessoal dos postos")
    posicao: int = Field(description="a posição na receita do ano; empate repete e pula")
    participacao: float = Field(description="a parte do cliente na receita do ano, de 0 a 1")
    participacao_acumulada: float = Field(
        description="a curva de Pareto: a soma dos maiores até este, de 0 a 1"
    )


class PontoDoPosto(BaseModel):
    """O ponto de um posto num mês, por situação do dia (`fato.ponto_dia`)."""

    status: str = Field(description="NORMAL, FALTA, ATESTADO ou FERIADO")
    dias: int = Field(description="quantos dias-pessoa tiveram esta situação")
    pessoas: int = Field(description="quantas pessoas distintas")
    horas_trabalhadas: float = Field(description="a soma das horas trabalhadas nesses dias")


class FunilDoTrimestre(BaseModel):
    """As candidaturas inscritas no trimestre e onde pararam (`fato.candidatura`)."""

    trimestre: int = Field(description="1 a 4, pela data de inscrição")
    candidaturas: int
    triadas: int = Field(description="chegaram à triagem")
    entrevistadas: int = Field(description="chegaram à entrevista interna")
    encaminhadas: int = Field(description="chegaram ao encaminhamento ao cliente")
    aprovadas: int
    admitidas: int = Field(description="aprovadas que viraram contrato de trabalho")
    reprovadas: int
    desistencias: int
    dias_medios_no_funil: float | None = Field(
        description="da inscrição à conclusão, nas concluídas"
    )


class Escopo(BaseModel):
    """Um recorte do Novo CAGED (`dim.escopo_mercado`)."""

    id: int
    territorio: str
    nivel: str = Field(description="município ou estado")
    grupo: str = Field(description="o grupo de atividade (CNAE)")
    segmento_da_fictalent: bool = Field(description="o grupo em que a Fictalent atua")


class MercadoDoMes(BaseModel):
    """O mercado formal de um escopo num mês (`fato.mercado_mes`)."""

    mes_id: int
    admissoes: int
    desligamentos: int
    saldo: int = Field(description="admissões menos desligamentos")


class Erro(BaseModel):
    detalhe: str
