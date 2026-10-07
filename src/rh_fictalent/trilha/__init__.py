"""A trilha de auditoria, pronta para ler: quem acessou, o que mudou, o que saiu, o que rodou.

O pipeline já grava tudo isto em quatro lugares, sem dado pessoal: o log de auditoria e a
matriz de permissão do sistema do cliente, na silver (o login virou chave, o valor alterado
não entra); a trilha de exclusões da réplica, na bronze; as execuções do Dagster e os descartes
da LGPD, no warehouse; e os consumidores e pedidos da API, também no warehouse. O que faltava
eram as perguntas prontas, com a resposta no grão em que um auditor pergunta: por perfil, por
filial, por mês, por tabela, por papel. É isso que `trilha.consultas` declara e que a linha de
comando (`python -m rh_fictalent.trilha`) responde, em tabela ou num relatório em pasta.
"""
