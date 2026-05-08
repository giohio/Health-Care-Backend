#!/bin/bash
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "postgres" <<-EOSQL
    CREATE DATABASE authentication;
    CREATE DATABASE patient_db;
    CREATE DATABASE doctor_db;
    CREATE DATABASE appointment_db;
    CREATE DATABASE notification_db;
    CREATE DATABASE clinical_db;
    CREATE DATABASE emr_result_db;
    CREATE DATABASE triage_session_db;
EOSQL
 