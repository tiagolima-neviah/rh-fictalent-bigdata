"""O que o pipeline faz para cumprir a LGPD depois que o dado chega ao lake.

- `descarte`: a eliminação (linha apagada na origem) e a retenção (candidato não contratado
  com prazo vencido) apagam o dado pessoal da bronze, com conferência e registro.

A pseudonimização da silver mora na própria silver (`rh_fictalent.silver.pseudonimizacao`),
porque é parte de como a silver é construída; as etiquetas que dizem o que é dado pessoal
moram com a DDL (`rh_fictalent.staging.lgpd`).
"""
