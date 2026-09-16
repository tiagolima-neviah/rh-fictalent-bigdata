# ADR-0004 · SeaweedFS como storage S3 do lake

**Situação:** aceito em 15/09/2026 (no card 2.1). Já de pé.

## Contexto

O lake (bronze, silver e gold em parquet) precisa de um storage separado do processamento, endereçado por `s3://`, para que o mesmo código rode na máquina do analista e num provedor de nuvem só trocando o endereço (via fsspec). A escolha óbvia até 2025 era o MinIO.

## Decisão

SeaweedFS 4.47 em container, falando a API S3, com identidade gerada no arranque a partir do `.env` (nada versionado) e bucket criado por um job idempotente.

## Alternativas consideradas

| alternativa | por que não |
|---|---|
| MinIO | a imagem da edição comunitária deixou de ser publicada no Docker Hub; a última no quay.io é de setembro de 2025, sem atualização de segurança há um ano, e reprovaria no trivy. Um projeto que ensina segurança não pode depender de imagem abandonada |
| disco local (`file://`) | não prova o endereço `s3://` nem a separação entre storage e processamento; serve só como atalho de desenvolvimento, que o fsspec já dá de graça |
| nuvem real (S3, GCS, R2) | credencial e custo fora do free tier para quem reproduz o projeto; entra como destino opcional, não como base |
| Garage, RustFS | alternativas válidas, menos conhecidas no mercado e com menos histórico; sem vantagem que justifique a troca |

## Consequências

- `S3_ACCESS_KEY` e `S3_SECRET_KEY` obrigatórios no `.env`; healthcheck em `/cluster/healthz`; bucket `fictalent-lake`.
- O código do lake fala fsspec e nunca SeaweedFS: trocar o storage é trocar uma URL.
- Se o SeaweedFS mudar de licença ou parar de publicar imagem, este ADR é revisto.
