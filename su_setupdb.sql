CREATE ROLE heatmapadmin LOGIN
NOSUPERUSER INHERIT NOCREATEDB NOCREATEROLE;

CREATE ROLE heatmapuser LOGIN
NOSUPERUSER INHERIT NOCREATEDB NOCREATEROLE;

ALTER ROLE heatmapadmin SET search_path = heatmap, public;
ALTER ROLE heatmapuser SET search_path = heatmap, public;

CREATE DATABASE heatmap_test
    WITH OWNER = heatmapadmin
    ENCODING = 'UTF8'
    TABLESPACE = pg_default
    LC_COLLATE = 'en_US.UTF-8'
    LC_CTYPE = 'en_US.UTF-8'
    CONNECTION LIMIT = -1;

/*on heatmap_test database*/
CREATE EXTENSION hstore; /*create in the public schema*/

