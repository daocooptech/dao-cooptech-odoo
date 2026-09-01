#!/usr/bin/env bash
# Запуск стенда. База уже собрана в setup.sh, здесь только поднимаем сервер.
set -eu
STAND=/stand
pkill -f "odoo -c" 2>/dev/null || true
nohup odoo -c "$STAND/odoo.conf" > "$STAND/odoo.log" 2>&1 &
echo "Стенд запускается. Порт 8069 открыт всем по ссылке из вкладки Ports."
echo "Вход: admin/admin (платформа) или vodyanov/vodyanov (пайщик)."
