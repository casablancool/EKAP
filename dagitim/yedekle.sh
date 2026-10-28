#!/usr/bin/env bash
# Her calismadan once veritabanini yedekler; 14 gunden eski yedekleri siler.
set -euo pipefail
cd "$(dirname "$0")/.."

DB=veri/ekap.db
[ -f "$DB" ] || { echo "veritabani henuz yok, yedek atlandi"; exit 0; }

mkdir -p veri/yedek
sqlite3 "$DB" ".backup veri/yedek/ekap-$(date +%F-%H%M).db"
find veri/yedek -name 'ekap-*.db' -mtime +14 -delete
