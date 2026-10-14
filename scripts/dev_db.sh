#!/usr/bin/env bash
# Start the local dev PostgreSQL (sandbox only). Idempotent. Data dir: /var/lib/postgresql/seqdata, port 5433.
D=/var/lib/postgresql/seqdata
pg_isready -q -h /tmp -p 5433 && { echo "postgres already running"; exit 0; }
rm -f $D/postmaster.pid
su postgres -c "/usr/lib/postgresql/16/bin/pg_ctl -D $D -o '-p 5433 -k /tmp' -l /var/lib/postgresql/seqdata.log -w start" | tail -1
