#!/bin/bash
# Postgres init script: create the two databases the platform needs.
set -e
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-EOSQL
    CREATE DATABASE app;
    CREATE DATABASE warehouse;
    GRANT ALL PRIVILEGES ON DATABASE app TO $POSTGRES_USER;
    GRANT ALL PRIVILEGES ON DATABASE warehouse TO $POSTGRES_USER;
EOSQL
