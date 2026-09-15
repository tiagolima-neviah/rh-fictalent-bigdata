#!/bin/sh
# Job de inicialização: cria o bucket do lake, se ainda não existir, e termina.
# Idempotente: rodar de novo não apaga nem recria nada.
set -eu

BUCKET="${S3_BUCKET:-fictalent-lake}"

if echo "s3.bucket.list" | weed shell -master=s3:9333 2>/dev/null | grep -q "^  ${BUCKET}"; then
  echo "bucket ${BUCKET} já existe"
  exit 0
fi

echo "s3.bucket.create -name ${BUCKET}" | weed shell -master=s3:9333
echo "bucket ${BUCKET} criado"
