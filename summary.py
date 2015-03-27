#!/usr/bin/env python3
"""
    This file contains the code that:
    1) retrieves data from the summary service on a term by term basis
    2) maintains records for common terms (cache)
    3) manages the provenance for specific heatmaps that have been saved
    4) maintains collapse maps??? or should this happen independently?
    5) calls into the ontology to traverse the graph

"""

import psycopg2
import requests
import libxml2

from IPython import embed

#SHOULD PROV also be handled here?
#SHOULD odering of rows and columns go here? NO

### THINGS THAT GO ELSEWHERE
# SCIGRAPH EXPANSION DOES NOT GO HERE
# REST API DOES NOT GO HERE



#the number of columns IS NOT STATIC
#the ORDER of the columns in the source is also NOT STATIC
#the mapping is to identifiers
#we must use a dict/hstore and THEN map to columns
#the dict is singular and provides the translation for fast lookup and manages history and changes
#the dict should probably be versioned and only track deltas so that we do not have to duplicate rows

###
#   Base urls that may change, and identifiers that need to be defined early
###

SCIGRAPH = "http://matrix.neuinfo.org:9000"
LITERATURE_ID = 'nlx_82958'  #FIXME pls no hardcode this (is a lie too)

###
#   The index/dict that maps columns to ids
###

'''
class datasource_index:
    """
        columns are only added, never removed
        they day this becomes a problem we will deal with it
        this is important for being able to say "this database did not exist back then"
    """
    def __init__(self):
        self.keys_ = []  #use a list to perserve order?
        self.dict_ = {}  #FIXME populate
    def __getitem__(self, key):
        return self.dict_[key]
    def __setitem__(self, key, value):
        if key not in self.dict_:
        else:
            self.dict_[key] = value
    def get(self, key):
        return self.__
'''

class _datasource_index:
    """
        AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAHHHHHHHHHHH
        THIS IS INSANE
    """
    dbname = "cm"
    user = "cm"
    host = "postgres-stage@neuinfo.org"
    port = 5432
    sql = "select distinct view_nif_id from view_sources order by view_nif_id;"
    def __init__(self):
        conn = pg.connect(dbname=self.dbname, user=self.user, host=self.host, port=self.port)
        cur = conn.cursor()
        try:
            cur.execute(self.sql)
            self.nifIds = cur.fetchall()
        except:
            raise
        finally:
            cur.close()
            conn.close()


    ##
    # select distinct view_nif_id from view_sources order by view_nif_id;  # run this on the concept mapper to populate
    # WHERE IN THE HELL DOES view_nif_id COME FROM!?!??!?!?!?!

class datasource_index:
    """
        the complete and utter madness that is the summary services has led me
        to the conclusion that the only way forward is to pull the bloody ids
        directly from said summary service and stick them in their own table
        THIS SEEMS MONUMENTALLY STUPID
    """


###
#   base class for getting XML from various servies
###

class rest_service:
    """ base class for things that need to get json docs from REST services
    """
    _timeout = 1
    _cache_xml = 0  #FIXME we may want to make this toggle w/o having to restart all the things
    def __new__(cls, *args, **kwargs):
        """ here for now to all hardcoded cache stuff """
        if cls._cache_xml:
            cls._xml_cache = {}
        instance = super().__new__(cls)
        return instance

    def get_xml(self, url):
        """ returns the raw xml for parsining """
        response = requests.get(url, timeout=self._timeout)
        if self._cache_xml:
            self._xml_cache[url] = response.text

        if response.ok:
            
            return response.text
        else:
            raise IOError("Get failed %s %s"%(reaponse.status_code, response.reason))

    def get_json(self, url):  #FIXME we should be able to be smart about this
        """ returns a dict/list combo structure for the json """
        response = requests.get(url, timeout=self._timeout)
        if response.ok:
            return response.json()
        else:
            raise IOError("Get failed %s %s"%(reaponse.status_code, response.reason))


    def xpath(self, xml, *queries):
        """
            run a set of xpath queries
            TODO: consider switching lxml for libxml2?
        """
        try:
            xmlDoc = libxml2.parseDoc(xml)
        except libxml2.parserError:
            raise

        context = xmlDoc.xpathNewContext()
        results = [context.xpathEval(query) for query in queries]

        if len(results) == 1:
            return results[0]
        else:
            return tuple(results)


###
#   Retrieve summary per term
###

class summary_service(rest_service):  # FIXME implement as a service/coro? with asyncio?
    url = "http://nif-services.neuinfo.org/servicesv1/v1/summary.xml?q=%s"
    _timeout = 10

    def __init__(self, term_server):  # FIXME this feels wrong :/
        self.term_server = term_server

    def get_sources(self):
        """
            get the complete list of data sources
            the structure for each nifid is as follows:

            (database name, indexable, total results)
        """
        query_url = self.url % '*'
        xml = self.get_xml(query_url)
        nodes, lit = self.xpath(xml, '//results/result', '//literatureSummary/@resultCount')
        resource_data_dict = {}

        # tuple order: db, indexable, total count ... NOTE db is the name
        resource_data_dict[LITERATURE_ID] = ('Literature', 'Literature', int(lit[0].content))

        for node in nodes:
            if node.prop('nifId') not in resource_data_dict:  # cull dupes
                nifId = node.prop('nifId')
                db = node.prop('db')
                indexable = node.prop('indexable')
                putative_count = node.xpathEval('./count')
                if len(putative_count) > 1:
                    print(term_id, name, [c.content for c in putative_count])
                    raise IndexError('too many counts!')
                count = int(putative_count[0].content)
                resource_data_dict[nifId] = db, indexable, count

        return resource_data_dict
        


    
    def get_counts(self, term):
        """
            given a term return the summary counts for each unique nifid
            full descriptions for each nifid do not duplicated here
            store once for all the records when we get that data
        """

        term_id = self.term_server.get_id(term)

        if term_id:  # get_id returns None if > 1 id
            query_url = self.url % term_id
        else:  # let the summary service sort out the id mess
            query_url = self.url % term

        xml = self.get_xml(query_url)
        nodes, name, lit = self.xpath(xml, '//results/result', '//clauses/query',
                                      '//literatureSummary/@resultCount')

        #TODO deal with names and empty nodes
        name = name[0].content
        if name != term:
            raise TypeError('for some reason name != term: %s != %s'%(name, term))

        nifid_count = {}

        #datasources
        for node in nodes:
            if node.prop('nifId') not in nifid_count:  # cull dupes
                nifId = node.prop('nifId')
                putative_count = node.xpathEval('./count')
                if len(putative_count) > 1:
                    print(term_id, name, [c.content for c in putative_count])
                    raise IndexError('too many counts!')
                count = int(putative_count[0].content)
                nifid_count[nifId] = count
        
        #literature
        nifid_count[LITERATURE_ID] = int(lit[0].content)

        return nifid_count



###
#   Map terms to ids  FIXME we need some way to resolve multiple mappings to ids ;_;
###

class term_service(rest_service):
    """ let us try this with json: result--works pretty well """
    url = SCIGRAPH + "/scigraph/vocabulary/term/%s.json?limit=20&searchSynonyms=true&searchAbbreviations=false&searchAcronyms=false"  #FIXME curie seems borken?
    _timeout = 1

    def get_id(self, term):
        query_url = self.url % term
        records = self.get_json(query_url)['concepts']
        if len(records) == 1:
            return records[0]['fragment']
        else:
            return None

###
#   Ontology services
###

class ontology_service(rest_service):
    url = None # XXX FIXME neighbors is currently broken :( :( :(
    def get_terms(self, term):
        return None

###
#   Stick the collected data in a datastore (postgres)
###

#table 

"""
CREATE EXTENSION hstore;

CREATE TABLE heatmap_history(
    id integer,
    doi text,
    DateTime 
)

CREATE TABLE term_history(
    "DateTime" timestamp without time zone,
     
)

CREATE TABLE term_hstores(
    term text,
    src_counts hstore,
)


CREATE TABLE view_history(
    id integer NOT NULL,
    source_id_order text[],
    CONSTRAINT view_history_pkey PRIMARY KEY (id)
)

CREATE TABLE view_data(
    version_id text,
    column_ids interger NOT NULL,
    term_counts hstore,
    CONSTRAINT view_data_id_fkey FOREIGN KEY (column_ids)
        REFERENCES view_history (id) MATCH SIMPLE
        ON UPDATE NO ACTION ON DELETE NO ACTION,
)

INSERT INTO view_history (id, source_id_order, term_counts) VALUES (
1,
'{"a", "b", "c"}',
'brain => "[1 2 3 4]"'
);

SELECT * FROM view_sources LEFT OUTER JOIN source_entity ON REPLACE(view_sources.src_nif_id,'_','-')=source_entity.nif_id;

SELECT nif_id FROM relation_entity WHERE is_view=TRUE;
"""

class database_service:
    dbname = "cm"
    user = "cm"
    host = "postgres-stage@neuinfo.org"
    port = 5432
    def __init__(self):
        pass

###
#   main
###

def main():
    ts = term_service()
    ss = summary_service(ts)
    test_url = "http://matrix.neuinfo.org:9000/scigraph/graph/neighbors/UBERON_0000955.json?depth=10&blankNodes=false&relationshipType=BFO_0000050&direction=both"
    embed()



if __name__ == '__main__':
    main()
