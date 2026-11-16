#!/bin/zsh
# Copies what the eval needs from the local machine into data/ (gitignored):
# your card statement CSVs, and your hand-entered expenses and category names
# from the local Postgres. Read-only against the database. Local use only:
# it refuses to run against anything but localhost.
#
#   ./scripts/export_local_data.sh /path/to/folder/with/statement/csvs
set -euo pipefail
statements="${1:?usage: export_local_data.sh /path/to/folder/with/statement/csvs}"
here="${0:A:h}/.."
root="$here/.."
data="$here/data"
mkdir -p "$data/statements"

git -C "$here" check-ignore -q data/ || { echo "data/ is not gitignored; stopping." >&2; exit 1; }

cp "$statements"/*.csv "$data/statements/"

set -a; source "$root/BE/.env"; set +a
if [[ "$DB_HOST" != "127.0.0.1" && "$DB_HOST" != "localhost" ]]; then
  echo "DB_HOST is $DB_HOST, not local; stopping." >&2; exit 1
fi
q() { PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "${DB_PORT:-5432}" -U "$DB_USERNAME" -d "$DB_DATABASE" -v ON_ERROR_STOP=1 -c "$1"; }

# Your own rows only (user_id null in local no-auth mode); the generated demo
# rows under another user id are left out (PLANS.md, "Context from the local data check").
q "\copy (select date_posted, description, category, amount, account, currency from expenses where user_id is null) to '$data/expenses.csv' csv header"
# The names you can pick on review: subcategories, as in the app's picker.
q "\copy (select name from categories where parent_category_id is not null order by name) to '$data/categories.csv' csv header"

echo "Wrote $(ls "$data/statements" | wc -l | tr -d ' ') statement files, expenses.csv and categories.csv to data/"
