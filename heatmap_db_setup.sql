-- 0 create user--
DO
$body$
BEGIN
    IF NOT EXISTS ( SELECT * FROM pg_catalog.pg_user
        WHERE usename = 'heatmapuser') THEN
        CREATE ROLE heatmapuser LOGIN
        NOSUPERUSER INHERIT NOCREATEDB NOCREATEROLE;
    END IF;
END;
$body$

-- 1 do alter role--
ALTER ROLE heatmapuser SET search_path = heatmap;

-- 2 drop db must be done alone--
DROP DATABASE IF EXISTS heatmap_test;

-- 3 create db must be done alone--
CREATE DATABASE heatmap_test
    WITH OWNER = heatmapuser
    ENCODING = 'UTF8'
    TABLESPACE = pg_default
    LC_COLLATE = 'en_US.UTF-8'
    LC_CTYPE = 'en_US.UTF-8'
    CONNECTION LIMIT = -1;

-- 4 do db settings, schema-- /*now connect to the database and make some tables*/

GRANT ALL ON DATABASE heatmap_test TO heatmapuser;

CREATE SCHEMA heatmap
    AUTHORIZATION heatmapuser;

GRANT ALL ON SCHEMA heatmap TO heatmapuser;


-- 5 create tables--
CREATE EXTENSION hstore SCHEMA heatmap;

SET SCHEMA 'heatmap';

CREATE TABLE heatmap_prov(
    id serial NOT NULL,
    doi text,
    /*requesting_person text,  *//* ARGH THE DESIRE TO NORMALIZE we can do this with the dois later if we really want to, RI is not critical*/
    "DateTime" timestamp without time zone,
    CONSTRAINT heatmap_prov_pkey PRIMARY KEY (id)
);

CREATE TABLE term_history(
    id serial NOT NULL,
    term text,
    term_counts hstore,
    CONSTRAINT term_history_pkey PRIMARY KEY (id)
);

CREATE TABLE heatmap_prov_to_term_history(  /* we need this for the many-many mapping */
    heatmap_prov_id integer,
    term_history_id integer,
    CONSTRAINT heatmap_prov_id_fkey FOREIGN KEY (heatmap_prov_id)
        REFERENCES heatmap_prov (id) MATCH SIMPLE
        ON UPDATE NO ACTION ON DELETE NO ACTION, /* we should never be deleting from these...*/
    CONSTRAINT term_history_id_fkey FOREIGN KEY (term_history_id)
        REFERENCES term_history (id) MATCH SIMPLE
        ON UPDATE NO ACTION ON DELETE NO ACTION
);

-- 6 do alters--
ALTER TABLE heatmap_prov OWNER TO heatmapuser;
ALTER TABLE term_history OWNER TO heatmapuser;
ALTER TABLE heatmap_prov_to_term_history OWNER TO heatmapuser;
--

/* We don't need this table :)
CREATE TABLE term_hstores(
    term text,
    src_counts hstore,
    CONSTRAINT term_hstores_pkey PRIMARY KEY (term)
);
*/

/*  I almost think that we don't need this since we are just going to hold all
the data in memory anyway and can repopulate from  * if needed, mappings from
view_nif_id -> names and other things should not be handled here, they are
already well managed somewhere else

CREATE TABLE summary_view_entity(
    view_nif_id text,
    name text,
);
*/

--ALTER TABLE term_hstores OWNER TO heatmapuser;
