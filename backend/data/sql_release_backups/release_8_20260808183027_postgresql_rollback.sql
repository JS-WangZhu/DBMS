-- SQL release #8 PostgreSQL partial rollback
-- database: app
-- generated_at: 2026-08-08T18:30:27
BEGIN;
-- rollback for statement #1
INSERT INTO "public"."test" ("id", "tt", "tta", "ttb") VALUES (12,NULL,NULL,NULL);
COMMIT;
