<a id="topo"></a>

# Régua de validação · o contrato de aceite do dado sintético

<!-- nav:start -->
[Home](../README.md) | [← Segurança e LGPD](05_seguranca_e_lgpd.md) | [Instalação e Reprodução →](07_instalacao_e_reproducao.md)
<!-- nav:end -->

> Dado sintético só serve se contar a história do caso, e "parece plausível" não é critério. Antes de existir uma linha de dado, este projeto escreveu o que a base precisava mostrar para ser aceita: 166 checks, cada um com um alvo e uma tolerância. Depois o gerador rodou, e a régua conferiu. Este documento explica o contrato, mostra de onde vem cada número e dá o comando para você conferir o veredito na sua máquina. Estado atual: **166 de 166 aprovados**, com as medidas e o laudo versionados em [`dados/regua`](../dados/regua/README.md).

## 1. A ideia: primeiro a banda, depois o dado

A Fictalent é uma empresa inventada com uma história precisa ([Entendimento do Negócio](01_entendimento_negocio.md)): cresce de 2018 a 2024, a qualidade do serviço cede a partir de 2023, os clientes começam a sair no fim de 2025, e mesmo assim nenhum ano fecha no vermelho. O painel, os indicadores e a análise do fim do projeto só fazem sentido se o dado carregar essa história, na proporção certa e sem saltos que entreguem que foi fabricado.

O método tem três regras:

1. **A banda vem antes do dado.** Cada número que a base precisa mostrar foi escrito como alvo mais tolerância antes de o gerador existir. Quem gera não escolhe o critério pelo qual será julgado.
2. **Reprovou, regenera.** Se um check reprova, o que se ajusta é o gerador. O dado nunca é remendado à mão, porque dado remendado não se reproduz.
3. **Mudar a banda é mudar o contrato.** Acontece (uma estimativa do rascunho pode estar errada), mas entra com data e motivo no histórico de [`bandas.py`](../src/rh_fictalent/validacao/bandas.py). A seção 6 lista cada revisão.

A régua confere **a história**, não o esquema. Coluna, tipo, nulo e domínio são assunto do pandera, nos arquivos e nas camadas do lake ([ADR-0006](adr/0006-pandera-e-regua.md)).

## 2. Como funciona

Quatro peças, todas em [`src/rh_fictalent/validacao`](../src/rh_fictalent/validacao):

| peça | o que é |
|---|---|
| **medida** | um número que a base entrega, com nome e chave: `headcount_medio/2024`, `sujeira/CAD-01`. O formato é um JSON `{medida: {chave: valor}}` |
| **banda** | o intervalo aceito: em torno de um alvo (tolerância relativa ou absoluta), só mínimo, só máximo, ou exatamente zero |
| **check** | código, família, descrição, a medida que consome e a banda. `E-02/2024`: headcount médio de 2024 entre 810 e 990 |
| **laudo** | o resultado de todos os checks: aprovado, reprovado ou pendente (a medida não veio). O veredito é **aprovada**, **reprovada** ou **incompleta** |

A régua não sabe gerar dado nem ler banco: recebe medidas e devolve um laudo. Por isso serve ao gerador hoje e pode conferir, mais adiante, as mesmas medidas tiradas do warehouse.

```bash
.venv/bin/python -m rh_fictalent.validacao --contrato                          # o que a régua espera receber
.venv/bin/python -m rh_fictalent.validacao --medidas dados/regua/medidas.json  # o laudo; sai 0, 1 ou 2
```

O código de saída é o veredito: 0 aprovada, 1 reprovada, 2 incompleta. Um pipeline pode parar nele.

## 3. As seis famílias

| família | checks | o que confere | de onde vem o alvo |
|---|---|---|---|
| 1 · escala e forma | 50 | clientes ativos, headcount médio e de pico, vagas abertas (tudo por ano), o mix de serviços de 2024 e o volume das maiores tabelas | a narrativa do caso, ano a ano |
| 2 · naturalidade | 4 | nada acontece "de uma vez": o headcount não salta contra a média móvel, clientes não entram nem saem em bloco, fora dos choques declarados (fundação, pandemia, crise) | decisão de desenho: dado fabricado se entrega pelos degraus |
| 3 · a história | 82 | oito indicadores de qualidade de serviço por ano, a defasagem entre a queda de qualidade e a perda de contrato, e a margem líquida | a degradação que explica 2025, e a regra de nunca fechar no vermelho |
| 4 · sazonalidade | 6 | o ritmo do ano (admissões e desligamentos por mês) contra o índice sazonal do Novo CAGED para o setor no estado | dado público, em [`dados/publicos/caged`](../dados/publicos/caged/README.md) |
| 5 · coerência interna | 6 | invariantes que não admitem nenhuma violação: alocação sem contrato de trabalho, ponto sem alocação, fatura sem contrato, folha que não fecha com o rateio, duas pessoas na mesma posição; e, desde a v0.6.0, a conservação de linhas entre a réplica e a bronze do lake (C-06) | o modelo de dados; a ingestão |
| 6 · sujeira | 18 | cada defeito do catálogo na proporção combinada, nem mais, nem menos | o catálogo de sujeira do caso |

### A história em números

O que a família 3 exige é o coração do caso. A operação é estável até 2022 e cede de 2023 em diante; cada indicador tem uma banda por ano, e a tabela mostra as pontas:

| indicador | até 2022 | 2025 |
|---|---|---|
| H-01 · time to fill de temporário (mediana, dias úteis) | 4 a 7 | 10 a 12 |
| H-02 · time to fill de R&S efetivo (mediana, dias úteis) | 14 a 20 | 25 a 29 |
| H-03 · no-show de entrevista | 10% a 16% | 23% a 27% |
| H-04 · no-show de primeiro dia | 3,5% a 6,5% | 10,5% a 13,5% |
| H-05 · turnover nos primeiros 90 dias | 12% a 18% | 27% a 33% |
| H-06 · dias descobertos por posição contratada por mês | 1,1 a 1,9 | 3,6 a 4,4 |
| H-07 · fill rate | 93% a 97% | 80% a 84% |
| H-08 · reclamações por 100 postos por mês | 0,5 a 1,1 | 2,3 a 2,9 |

Dois checks amarram a narrativa. **H-09**: entre a qualidade cair abaixo do tolerável e o cliente romper o contrato passam de 6 a 9 meses (mediana). Esse intervalo não é parâmetro do gerador: o cliente só decide perto da renovação, olhando os últimos meses de serviço, e a defasagem aparece sozinha. **H-10**: a margem líquida segue a tabela do caso (de 3% em 2020 a 12% em 2023 e 2024, e 4% em 2026) e é positiva em todos os anos.

### A sujeira, na medida

O banco é sujo de propósito ([Entendimento dos Dados](02_entendimento_dados.md), seção 11). A régua garante que cada defeito existe na proporção em que a auditoria de qualidade vai encontrá-lo:

| código | defeito | alvo |
|---|---|---|
| CAD-01 | candidato duplicado, com outra grafia | 3,5% dos candidatos |
| CAD-02 | CPF com dígito verificador inválido | 0,8% |
| CAD-03 | data de nascimento impossível | 0,2% |
| PES-01 | admissão lançada depois do fato | 6% até 2022, 11% desde 2024 |
| PES-02 | temporário além de 180 ou 270 dias sem aditivo | 1,8%, com pelo menos 60% dos casos de 2023 em diante |
| PON-01 | dia com marcação de ponto faltante | 2,5% |
| PON-02 | dia com marcação duplicada | 0,6% |
| SST-01 | ASO vencido com a pessoa alocada | 4% dos alocados em 2024 e em 2025 (média dos fins de mês) |
| FIN-01 | título recebido com valor diferente, sem registro de desconto | 1,2% dos pagos |
| GER-01 | consolidado gerencial divergindo da operação | zero até 2021; de 0,5% em 2022 a 9% em 2026, e nunca batendo desde 2022 |

## 4. O aceite: a base inteira contra a régua inteira

Cada etapa do gerador já confere a própria parte quando roda (a régua parcial sai junto na linha de comando). O aceite é a prova de ponta a ponta:

```bash
.venv/bin/python -m rh_fictalent.gerador --aceite --replica
```

Gera as seis etapas em memória (35 segundos, pico de 2,3 GB de RAM), roda a conferência de cada uma, junta as medidas de todas (a mesma medida vinda de duas etapas tem de ser o mesmo número), conta as linhas de cada tabela **na réplica** (têm de ser as que o gerador produz, tabela a tabela) e passa a régua. Aprovando, escreve `dados/regua/medidas.json` e `dados/regua/laudo.txt`.

Três garantias ficam nos testes, e portanto na CI:

- o laudo versionado aprova a régua inteira, sem check pendente;
- o laudo versionado é o da base que o gerador produz hoje: um teste gera a base e compara medida por medida. Mexeu no gerador e um número mudou, o aceite tem de ser refeito e versionado de novo;
- a réplica tem o que a etapa gera, linha a linha nas tabelas principais (os testes de réplica de cada etapa).

## 5. Onde a régua passa raspando

Aprovado não é folgado, e esconder isso seria vender o laudo por mais do que ele vale. Três checks aprovam perto da borda, e são os primeiros a olhar se o gerador mudar:

| check | valor | limite |
|---|---|---|
| S-01 · maior desvio mensal das admissões contra o CAGED | 0,449 | até 0,45 |
| E-06 · linhas em `folha.provisao` | 146.926 | até 148.200 |
| H-06 · dias descobertos em 2026 | 4,21 | até 4,4 |

## 6. Revisões do contrato

Toda mudança de banda está datada e motivada no topo de [`bandas.py`](../src/rh_fictalent/validacao/bandas.py). Até aqui:

| quando | o que mudou | por quê |
|---|---|---|
| 21/09/2026, ocupação dos postos | naturalidade: limite contra a média móvel de 0,35 para 0,45, e os choques declarados ganham o ano da fundação e a retomada de julho a setembro de 2020 | a subida de outubro para novembro passa de 35% nos anos de maior amplitude sem ser degrau; em 2018 a base é pequena e cada contrato pesa |
| 21/09/2026, ocupação dos postos | sazonalidade: correlação mínima com o CAGED sobe para 0,75; desvios máximos e médios ficam mais largos | a Fictalent vive de reforço de temporada: acompanha o ritmo do setor com amplitude maior que a do agregado estadual |
| 21/09/2026, financeiro | linhas de `financeiro.fatura_item` de 52 mil para 9,5 mil | o rascunho supunha um posto por posição; a carteira abre postos com quantidade |
| 21/09/2026, SST | linhas de `sst.aso` de 40 mil para 20 mil; SST-01 definido como prevalência no fim de cada mês | metade dos contratos de trabalho dura até 50 dias: quase todos têm só o admissional, e a NR-7 dispensa o demissional quando o último exame é recente |
| 23/09/2026, lake (card 6.1) | coerência: check novo **C-06**, tabelas cuja contagem de linhas vivas na bronze difere da réplica, banda exatamente 0; a medida `conservacao` é calculada pelo aceite lendo o lake com DuckDB | a bronze é espelho da réplica, e espelho se prova contando; a régua passa de 165 para 166 checks |

Nenhuma revisão afrouxou um check que o dado reprovava por contar a história errada: duas corrigiram estimativas de volume do rascunho, duas trocaram um limite genérico por um que descreve o negócio (temporada), e a última não mexeu em banda nenhuma: acrescentou um check, porque a régua passou a alcançar uma camada que antes não existia.

## 7. O que a régua não faz

- **Não confere esquema.** Isso é do pandera, a partir da v0.5.0.
- **Não é teste estatístico.** Banda é intervalo em torno de alvo; não há p-valor nem intervalo de confiança. É contrato, não inferência.
- **Não mede na réplica.** As medidas são tiradas do que o gerador produz em memória; a réplica entra pela contagem de linhas de todas as tabelas e pelos testes que comparam, linha a linha, o que foi gravado com o que foi gerado. Medir por SQL no warehouse é trabalho das versões do lake e do gold, e a régua está pronta para receber essas medidas.
- **Não garante realismo fora do que confere.** O que a régua não mede pode estar errado. Um exemplo aconteceu: o funil de recrutamento rodava 24 horas por dia, sete dias por semana, e nenhum check olhava para a hora das entrevistas. Foi achado lendo o dado, corrigido no gerador e a base foi regenerada. A régua é necessária, não suficiente: olhar o dado continua sendo parte do trabalho.

---

[Início](#topo) | [Instalação e Reprodução →](07_instalacao_e_reproducao.md)
