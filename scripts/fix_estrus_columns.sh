#!/bin/bash
# 热修：estrus_states 补 created_at / updated_at（迁移 88 漏列）
set -a
source /etc/dzmm/dzmm.env
set +a
DB="${DZMM_DATABASE_URL/postgresql+psycopg/postgresql}"
psql "$DB" -c "ALTER TABLE estrus_states ADD COLUMN IF NOT EXISTS created_at timestamptz NOT NULL DEFAULT now();"
psql "$DB" -c "ALTER TABLE estrus_states ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now();"
psql "$DB" -c "SELECT column_name, data_type FROM information_schema.columns WHERE table_name='estrus_states' ORDER BY ordinal_position;"
cp /tmp/mig_88.py /opt/dzmm/current/migrations/versions/20261003_88_estrus_chop.py
