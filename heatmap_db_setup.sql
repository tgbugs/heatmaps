--create the user
CREATE ROLE heatmapuser LOGIN
    NOSUPERUSER INHERIT NOCREATEDB NOCREATEROLE;

ALTER USER heatmapuser SET search_path = heatmap;

--create the db
CREATE DATABASE heatmap_test
    WITH OWNER = heatmapuser
    ENCODING = 'UTF8'
    TABLESPACE = pg_default
    LC_COLLATE = 'en_US.UTF-8'
    LC_CTYPE = 'en_US.UTF-8'
    CONNECTION LIMIT = -1;

GRANT ALL ON DATABASE heatmap_test TO heatmapuser;

CREATE SCHEMA heatmap
    AUTHORIZATION heatmapuser;

GRANT ALL ON SCHEMA heatmap TO heatmapuser;

--now connect to the database and make some tables
CREATE EXTENSION hstore SCHEMA heatmap;

SET SCHEMA 'heatmap';

CREATE TABLE heatmap_prov(
    id integer,
    doi text,
    "DateTime" timestamp without time zone,
    CONSTRAINT heatmap_prov_pkey PRIMARY KEY (id)
);

CREATE TABLE term_history(
    heatmap_prov_id integer,
    term text,
    term_hstore hstore,
    CONSTRAINT heatmap_prov_id_fkey FOREIGN KEY (heatmap_prov_id)
        REFERENCES heatmap_prov (id) MATCH SIMPLE
        ON UPDATE NO ACTION ON DELETE NO ACTION
);

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

ALTER TABLE heatmap_prov OWNER TO heatmapuser;
ALTER TABLE term_history OWNER TO heatmapuser;
--ALTER TABLE term_hstores OWNER TO heatmapuser;
