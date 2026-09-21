# O aceite da base sintética

A base sintética da Fictalent só vale se passar na régua: 165 checks em seis famílias (escala e forma, naturalidade, a história do caso, sazonalidade contra o Novo CAGED, coerência interna e a sujeira na medida certa). O contrato está em [`validacao/bandas.py`](../../src/rh_fictalent/validacao/bandas.py), com cada revisão datada e motivada.

- `medidas.json`: os números que a base entrega, no formato do contrato (`{medida: {chave: valor}}`);
- `laudo.txt`: o veredito da régua sobre esses números, check a check.

Os dois saem do mesmo comando, que gera as seis etapas de ponta a ponta, confere cada uma, junta as medidas e conta as linhas na réplica (o laudo mede a base que está gravada, e ela tem de ser a que o gerador produz):

```bash
.venv/bin/python -m rh_fictalent.gerador --aceite --replica
```

Qualquer pessoa confere o veredito sem gerar nada:

```bash
.venv/bin/python -m rh_fictalent.validacao --medidas dados/regua/medidas.json
```

**Reprovou, regenera.** O que se ajusta é o gerador (ou a banda, com data e motivo); o dado nunca é remendado. Os testes garantem que este laudo é o da base que o gerador produz hoje: mexeu no gerador e uma medida mudou, o aceite tem de ser refeito e versionado de novo.
