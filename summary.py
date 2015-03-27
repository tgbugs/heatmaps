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

import numpy as np

from IPython import embed

#SHOULD PROV also be handled here?
#SHOULD odering of rows and columns go here? NO
# TODO probably need to make this work via cgi?

### THINGS THAT GO ELSEWHERE
# SCIGRAPH EXPANSION DOES NOT GO HERE  #FIXME but maybe running/handling the transitive closure does?
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
LITERATURE_ID = 'nlx_82958'  # FIXME pls no hardcode this (is a lie too)
TOTAL_TERM = 'federation_totals'  # FIXME we need to come up with a name for this though because * is reserved in sql

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
            raise IOError("Get failed %s %s"%(response.status_code, response.reason))

    def get_json(self, url):  #FIXME we should be able to be smart about this
        """ returns a dict/list combo structure for the json """
        response = requests.get(url, timeout=self._timeout)
        if response.ok:
            return response.json()
        else:
            raise IOError("Get failed %s %s"%(response.status_code, response.reason))


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
        self.resources = self._get_sources()  # TODO invalidate when keys or counts mismatch with a * query (beautiful)

    def _get_sources(self):
        """
            get the complete list of data sources
            the structure for each nifid is as follows:

            (database name, indexable, total results)

            check results against cm, but be aware that 
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

        # TODO once this source data has been retrieved we should really go ahead and make sure the database is up to date
        return resource_data_dict

    def check_counts(self):
        """ validate that we have the latest, if we do great
            otherwise flag all existing hstore cache values as dirty
        """
        # XXX remind me again why we are sticking the non-proved stuff in a table?
        # shouldn't it just sit in python memory and be served out here?

        
    def get_counts(self, term):
        """
            given a term return the summary counts for each unique nifid
            full descriptions for each nifid do not duplicated here
            store once for all the records when we get that data
        """

        if term != "*":
            term_id = self.term_server.get_id(term)

            if term_id:  # get_id returns None if > 1 id
                query_url = self.url % term_id
            else:  # let the summary service sort out the id mess
                query_url = self.url % term
        else:
            query_url = self.url % term  #FIXME ICK

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
    url = SCIGRAPH + "/scigraph/vocabulary/term/%s.json?limit=20&searchSynonyms=true&searchAbbreviations=false&searchAcronyms=false"
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
    url = SCIGRAPH + "/scigraph/graph/neighbors/%s.json?depth=10&blankNodes=false&relationshipType=%s&direction=in"
    _timeout = 10
    def get_terms(self, term_id, relationship):
        query_url = self.url % (term_id, relationship)
        records = self.get_json(query_url)
        names = []
        for rec in records['edges']:
            if term_id in rec.values():
                for node in records['nodes']:
                    if node['id'] == rec['sub']:
                        names.append(node['lbl'])

        #FIXME the test on part of produces utter madness, tree is not clean
        return records, names

###
#   Stick the collected data in a datastore (postgres)
###

#table 

"""
INSERT INTO view_history (id, source_id_order, term_counts) VALUES (
1,
'{"a", "b", "c"}',
'brain => "[1 2 3 4]"'
);

SELECT * FROM view_sources LEFT OUTER JOIN source_entity ON REPLACE(view_sources.src_nif_id,'_','-')=source_entity.nif_id;

SELECT nif_id FROM relation_entity WHERE is_view=TRUE; --burak has a service for this
"""

class database_service:  # FIXME reimplement with asyncio?
    """ This should sort of be the central hub for fielding io for the database
        it should work for caching for the phenogrid output and for csv output
    """
    dbname = "heatmap"
    user = "heatmapuser"
    host = "localhost"#"postgres-stage@neuinfo.org"
    port = 5432
    def __enter__(self):
        self.conn = pg.connect(dbname=self.dbname, user=self.user, host=self.host, port=self.port)
    def __exit__(self):
        self.conn.close()

    def cursor_exec(self, SQL, args):
        cur = self.conn.cursor()
        cur.execute(SQL, args)
        tups = cur.fetchall()
        cur.close()
        return tups


class heatmap_service(database_service):

    def __init__(self):
        self.term_count_dict = {}
        self.term_dirty = {}

    def get_heatmap_data_from_doi(self, doi):
        sql = "SELECT th.term, th.term_hstore FROM heatmap_prov AS hp JOIN term_history AS th ON hp.id=th.heatmap_prov_id WHERE hp.doi=%s;"
        tuples = self.cursor_exec(sql, (doi,))
        hm_data = {term:hstore for term, hstore in tuples}
        return hm_data

    def get_heatmap_from_doi(self, doi, term_id_order=None, src_id_order=None):
        """ return default (alpha) ordereded heatmap or apply input orders
        """
        hm_data = self.get_heatmap_data_from_doi(doi)
        if not term_id_order:
            term_id_order = sorted(hm_data) 
        if not src_id_order:
            term_id_order = sorted(hm_data[TOTAL_TERM])
        heatmap = dict_to_matrix(hm_data, term_id_order, src_id_order)

    def make_heatmap_data(self, *terms):
        """ this call mints a heatmap and creates the prov record
            this is also where we will check to see if everything is up to date
        """
        #call to * to validate counts
        self.summary_server.check_counts()
        #

    def get_term_counts(self, *terms):
        """ given a collection of terms retunrs a dict of dicts of their counts
        """
        terms = tuple(set([TOTAL_TERM].extend(terms)))  #removes dupes
        sql = "SELECT src_counts FROM term_hstores WHERE term IN %s"
        term_hstores = self.cursor_exec(sql, (terms,))
        term_count_dict = {}
        for term, hstore in zip(terms,term_hstores):
            if not hstore:
                hstore = self.summary_server.get_counts(term)
                self.add_hstore(term, hstore)

            self.term_count_dict[term] = hstore

        return term_count_dict

    def add_counts(self, term, term_count_dict):


    def add_hstore(self, term, hstore):
        sql = "INSERT INTO term_hstores (term, src_counts) VALUES(%s, %s)"
        args = (term, hstore)
        self.cursor_exec(sql, args)

    def update_hstore(self, term, hstore):
        """ this is a giant pile of poop """
        sql = "DELETE FROM term_hstores WHERE term=%s"  # FIXME
        args = (term,)
        self.cursor_exec(sql, args)
        self.add_hstore(term, hstore)

    def output_csv(self, heatmap):
        """ consturct a csv file on the fly for download """


###
#   utility functions  FIXME these should probably go elsewhere?
###

def apply_order(dict_, key_order):
    """ applys an order to values of a dict based on an ordering of the keys
        if the dict to be ordered is missing a key that is in the order then
        a value of None is inserted in that position of the output list
    """
    ordered = []
    for key in key_order:
        try:
            ordered.append(dict_[key])
        except KeyError:
            ordered.append(None)
    return  ordered
                        

def dict_to_matrix(tdict_sdict, term_ids_order, src_ids_order):
    """ given heatmap data, and orders on sources and terms
        return a matrix representation
    """
    #sanity check
    if len(tdict_sdict) < len(term_ids_order):  # term_ids can be a subset!
        # note that we *could* allow empty terms in the dict but that should
        # be handled elsewhere
        raise IndexError("Term orders must be subsets of the dict!")
    if len(tdict_sdict[TOTAL_TERM]) != len(src_ids_order):  # these must match
        raise IndexError("Source orders must match the total source counts!")

    matrix = np.empty(len(term_ids_order), len(src_ids_order))
    for i, term in enumerate(term_ids_order):
        matrix[i,:] = apply_order(hm_data[term], src_ids_order)


###
#   main
###

def main():
    ts = term_service()
    ss = summary_service(ts)
    os = ontology_service()
    t = "UBERON_0000955"  # FIXME a reminder that these ontologies do not obey tree likeness and make everything deeply, deeply painful
    r = "BFO_0000050"
    j = os.get_terms(t, r)
    embed()



if __name__ == '__main__':
    main()
