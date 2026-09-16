# ADR-0008 · Gitflow com cada fase virando versão publicável

**Situação:** aceito em 15/09/2026. Em uso desde o primeiro card.

## Contexto

Repositório público, um autor com um assistente, revisão humana obrigatória antes de qualquer coisa entrar, e um objetivo explícito: cada bloco entregue precisa virar **evidência publicável** (versão com tag) que alimenta currículo e divulgação. A esteira de CI precisa ser portão, não decoração.

## Decisão

- Um card, uma branch `feature/<fase>.<card>-<nome>` saída de `develop`.
- Toda mudança entra por **pull request** para `develop` (branch padrão do repositório), com a CI verde como condição de merge.
- Cada fase fechada vira **versão**: PR de `develop` para `main` e tag SemVer (`v0.2.0`, `v0.3.0`, ...); a versão publicada dispara aviso ao consultor de carreira e à divulgação.
- Commits em ASCII, sem trailer de coautoria; branches apagadas ao mesclar.

## Alternativas consideradas

| alternativa | por que não |
|---|---|
| trunk-based (tudo em `main`) | não tem o momento de "versão publicável" nem o portão de revisão; adequado a times com CI e testes maduros num produto contínuo, não a um portfólio por blocos |
| GitHub flow (sem `develop`) | funciona, mas perde a integração por fase: a `main` receberia cards soltos, e a versão deixaria de coincidir com uma fase inteira, testada junto |
| sem PR (push direto) | perde a CI como portão e a revisão do dono do projeto, que é parte do método |

## Consequências

- O primeiro PR foi mesclado na `main` por engano porque a branch padrão ainda era `main`; a correção (padrão em `develop`, sincronização) virou regra do manual.
- "Automatically delete head branches" ligado; proteção de branch em `develop` exigindo a CI.
- O passo a passo do rito (branch, commit, push, PR, checks, merge, faxina, tag) é material de estudo do projeto.
