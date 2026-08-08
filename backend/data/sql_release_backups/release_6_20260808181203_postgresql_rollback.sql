-- SQL release #6 PostgreSQL partial rollback
-- database: app
-- generated_at: 2026-08-08T18:12:03
BEGIN;
-- rollback for statement #2
INSERT INTO "public"."test" ("id", "tt", "tta", "ttb") VALUES (11,NULL,NULL,NULL);
INSERT INTO "public"."test" ("id", "tt", "tta", "ttb") VALUES (11,'d','e','f');
-- rollback for statement #1
DELETE FROM "public"."test" WHERE ("id" IS NOT DISTINCT FROM 13 AND "tt" IS NOT DISTINCT FROM 'a' AND "tta" IS NOT DISTINCT FROM 'b' AND "ttb" IS NOT DISTINCT FROM 'c');
COMMIT;
