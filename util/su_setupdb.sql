-- setup for production heatmaps database
-- run each subsection independely, the /**/ comment section is /*user database*/
-- 0 create user-- /*postgres postgres*/
DO
$body$
BEGIN
    IF NOT EXISTS ( SELECT * FROM pg_catalog.pg_user
        WHERE usename = 'heatmapuser') THEN
        CREATE ROLE heatmapuser LOGIN
        NOSUPERUSER INHERIT NOCREATEDB NOCREATEROLE;
    END IF;
    IF NOT EXISTS ( SELECT * FROM pg_catalog.pg_user
        WHERE usename = 'heatmapadmin') THEN
        CREATE ROLE heatmapadmin LOGIN
        NOSUPERUSER INHERIT NOCREATEDB NOCREATEROLE;
    END IF;
END;
$body$

-- 1 do alter role /*postgres postgres*/--
ALTER ROLE heatmapadmin SET search_path = heatmap, public;
ALTER ROLE heatmapuser SET search_path = heatmap, public;

-- 2 create db must be done alone /*postgres postgres*/--
CREATE DATABASE heatmap
    WITH OWNER = heatmapadmin
    ENCODING = 'UTF8'
    TABLESPACE = pg_default
    /* NOTE the LC are broken on windows */
    LC_COLLATE = 'en_US.UTF-8'
    LC_CTYPE = 'en_US.UTF-8'
    CONNECTION LIMIT = -1;

-- 3 do db settings, schema /*postgres heatmap*/--

CREATE EXTENSION hstore;  /*keep this on public so heatmapuser cant bolox everything*/

