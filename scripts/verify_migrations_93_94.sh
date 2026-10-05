#!/bin/bash
set -a
source /etc/dzmm/dzmm.env
set +a
DB="${DZMM_DATABASE_URL/postgresql+psycopg/postgresql}"
echo "===== 93：estrus_settings 新列 ====="
psql "$DB" -c "SELECT column_name FROM information_schema.columns WHERE table_name='estrus_settings' AND column_name IN ('chopper_coin_p0','chopper_coin_p1','chopper_coin_p2','target_daily_limit','coins_linked','chopper_fixed_coins','target_fixed_coins');"
psql "$DB" -c "SELECT column_name FROM information_schema.columns WHERE table_name='estrus_chops' AND column_name='coins_deducted';"
psql "$DB" -c "SELECT indexname FROM pg_indexes WHERE tablename='estrus_chops' AND indexname='ix_estrus_chops_group_target_created';"
echo "===== 94：items 新列 + 新表 ====="
psql "$DB" -c "SELECT column_name FROM information_schema.columns WHERE table_name='items' AND column_name IN ('effect_config','configuration_version','deleted_at');"
psql "$DB" -c "SELECT column_name FROM information_schema.columns WHERE table_name='shop_purchases' AND column_name='item_snapshot';"
psql "$DB" -c "SELECT tablename FROM pg_tables WHERE tablename IN ('shop_catalog_state','shop_change_batches');"
echo "===== 94 数据回填抽查 ====="
psql "$DB" -c "SELECT count(*) AS items_with_config FROM items WHERE effect_config IS NOT NULL;"
psql "$DB" -c "SELECT count(*) AS purchases_snapshotted FROM shop_purchases WHERE item_snapshot IS NOT NULL;"
