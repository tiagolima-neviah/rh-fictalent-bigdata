#!/bin/sh
# Sobe o SeaweedFS com a API S3 e uma identidade de acesso gerada a partir do .env.
# O arquivo de identidade vive só dentro do container (/tmp), nunca no repositório.
set -eu

: "${S3_ACCESS_KEY:?S3_ACCESS_KEY ausente}"
: "${S3_SECRET_KEY:?S3_SECRET_KEY ausente}"

umask 077
cat > /tmp/s3.json <<JSON
{
  "identities": [
    {
      "name": "pipeline",
      "credentials": [
        { "accessKey": "${S3_ACCESS_KEY}", "secretKey": "${S3_SECRET_KEY}" }
      ],
      "actions": ["Admin", "Read", "List", "Tagging", "Write"]
    }
  ]
}
JSON

exec weed server -dir=/data -s3 -s3.port=8333 -s3.config=/tmp/s3.json -ip=s3 -ip.bind=0.0.0.0 -master.volumeSizeLimitMB=1024
