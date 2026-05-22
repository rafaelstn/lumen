#!/bin/sh
set -e

# Substitui apenas ${PORT} no template (preserva $uri e demais variáveis do Nginx).
envsubst '${PORT}' < /etc/nginx/nginx.conf.template > /etc/nginx/nginx.conf

exec nginx -g 'daemon off;'
