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

-- 2 drop db must be done alone /*postgres postgres*/--
DROP DATABASE IF EXISTS heatmap_test; /*should DROP TABLE for testing*/

-- 3 create db must be done alone /*postgres postgres*/--
CREATE DATABASE heatmap_test
    WITH OWNER = heatmapadmin
    ENCODING = 'UTF8'
    TABLESPACE = pg_default
    /* NOTE the LC are broken on windows */
    /*LC_COLLATE = 'en_US.UTF-8'
    LC_CTYPE = 'en_US.UTF-8'*/
    CONNECTION LIMIT = -1;

-- 4 do db settings, schema /*postgres heatmap_test*/--

CREATE EXTENSION hstore;  /*keep this on public so heatmapuser cant bolox everything*/

-- 5 create schemas and tables /*heatmapadmin heatmap_test*/--
GRANT CONNECT ON DATABASE heatmap_test TO heatmapuser;
CREATE SCHEMA IF NOT EXISTS heatmap;
GRANT USAGE ON SCHEMA heatmap TO heatmapuser;
    /*AUTHORIZATION heatmapadmin;*/

-- 6 create tables /*heatmapadmin heatmap_test*/--

CREATE TABLE heatmap_prov(
    id serial NOT NULL,
    /*doi text, */ /* just use the primary key and don't fiddle */
    /*requesting_person text,  *//* ARGH THE DESIRE TO NORMALIZE we can do this with the dois later if we really want to, RI is not critical*/
    datetime timestamp default CURRENT_TIMESTAMP,  /*enforce this in the db*/
    filename varchar(4096),  /* added, see alter table below*/
    CONSTRAINT heatmap_prov_pkey PRIMARY KEY (id)
);

/*
ALTER TABLE IF EXISTS heatmap_prov ADD filename varchar(4096);
 */

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
        ON UPDATE NO ACTION ON DELETE NO ACTION, /*we should never be deleting from these?*/
    CONSTRAINT term_history_id_fkey FOREIGN KEY (term_history_id)
        REFERENCES term_history (id) MATCH SIMPLE
        ON UPDATE NO ACTION ON DELETE NO ACTION
);

CREATE TABLE job_to_heatmap_prov(
    id serial NOT NULL,  /* simple is good */
    datetime timestamp default CURRENT_TIMESTAMP,  /*enforce this in the db*/
    heatmap_prov_id integer,
    CONSTRAINT job_id_pkey PRIMARY KEY (id),
    CONSTRAINT heatmap_prov_id_fkey FOREIGN KEY (heatmap_prov_id)
        REFERENCES heatmap_prov (id) MATCH SIMPLE
        ON UPDATE NO ACTION ON DELETE NO ACTION
);

-- 7 grant select and insert for the user on the new tables /*heatmapadmin heatmap_test*/--
GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA heatmap TO heatmapuser;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA heatmap TO heatmapuser;

-- 8 do alters, redundant if run as heatmapuser /*heatmapadmin heatmap_test*/--
ALTER TABLE heatmap_prov OWNER TO heatmapadmin;
ALTER TABLE term_history OWNER TO heatmapadmin;
ALTER TABLE heatmap_prov_to_term_history OWNER TO heatmapadmin;

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
