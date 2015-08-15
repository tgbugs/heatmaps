#!/usr/bin/env python3
"""
    This file contains the code that:
    1) retrieves data from the summary service on a term by term basis
    2) maintains records for common terms (cache)
    3) manages the provenance for specific heatmaps that have been saved
    4) maintains collapse maps??? or should this happen independently?
    5) calls into the ontology to traverse the graph

"""

import simplejson
from functools import wraps
from os import environ

import requests
import psycopg2 as pg
from psycopg2.extras import register_hstore
from lxml import etree

import numpy as np

if environ.get('HEATMAP_PROD',None):  # set in heatmaps.wsgi if not globally
    embed = lambda args: print("THIS IS PRODUCTION AND PRODUCTION DOESNT LIKE IPYTHON ;_;")
else:
    from IPython import embed


"""
INSERT INTO view_history (id, source_id_order, term_counts) VALUES (
1,
'{"a", "b", "c"}',
'brain => "[1 2 3 4]"'
);

SELECT * FROM view_sources LEFT OUTER JOIN source_entity ON REPLACE(view_sources.src_nif_id,'_','-')=source_entity.nif_id;

SELECT nif_id FROM relation_entity WHERE is_view=TRUE; --burak has a service for this
"""


#SHOULD PROV also be handled here?
#SHOULD odering of rows and columns go here? NO
# TODO probably need to make this work via cgi? (probably not cgi)
# TODO logging and perf

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
#   urls that may change, and identifiers that need to be defined globally
###

SCIGRAPH = "http://matrix.neuinfo.org:9000"
LITERATURE_ID = 'nlx_82958'  # FIXME pls no hardcode this (is a lie too)
TOTAL_TERM_ID = 'federation_totals'  # FIXME we need to come up with a name for this though because * is reserved in sql
TOTAL_TERM_ID_NAME = 'Totals'

###
#   Decorators
###
def sanitize_input(function):
    """ Right now this is just a reminder function to flag functions that
        need to have their input sanitized since they are inserted into the sql
    """
    @wraps(function)
    def wrapped(*args, **kwargs):
        return function(*args,**kwargs)
    return wrapped

###
#   base class for getting XML or json from various servies
###

class rest_service:  #TODO this REALLY needs to be async... with max timeout "couldnt do x terms"
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

    def get(self, url, response_type):
        response = requests.get(url, timeout=self._timeout)
        if response.ok:
            if response_type == 'xml':
                return response.text
            elif response_type == 'json':
                return response.json()
            else:
                return response.text
        else:
            raise ConnectionError("Get of %s failed %s %s"%(url, response.status_code, response.reason))

    def xpath(self, xml, *queries):
        """ Run a set of xpath queries. """
        try:
            xmlDoc = etree.fromstring(xml.encode())
        except etree.ParseError:
            raise  # TODO
        
        results = [xmlDoc.xpath(query) for query in queries]

        if len(results) == 1:
            return results[0]
        else:
            return tuple(results)


###
#   Retrieve summary per term
###

class summary_service(rest_service):  # FIXME implement as a service/coro? with asyncio?
    url = "http://nif-services.neuinfo.org/servicesv1/v1/summary.xml?q=%s"
    _timeout = 20

    @staticmethod
    def _walk_nodes(nodes, *keys):
        """ always return counts, any extra vals goes their own dict """
        resource_data_dict = {}
        nifid_count = {}
        for node in nodes:
            if node.get('nifId') not in resource_data_dict:  # cull dupes
                nifId = node.get('nifId')

                putative_count = node.xpath('./count')
                if len(putative_count) > 1:
                    print(TOTAL_TERM_ID, TOTAL_TERM_ID_NAME, [c.content for c in putative_count])
                    raise IndexError('too many counts!')  #FIXME we must handle this
                count = int(putative_count[0].text)
                nifid_count[nifId] = count

                if keys:
                    vals = tuple([node.get(key) for key in keys])
                    resource_data_dict[nifId] = vals

        if keys: print("KEYS?", keys)
        return (nifid_count, resource_data_dict) if keys else nifid_count

    def get_sources(self):
        """
            get the complete list of data sources
            the structure for each nifid is as follows:

            (database name, indexable)
            a dict of nifid_count_total is also returned matching the format
            of other nifid_count dictionaires, this one is considered to be
            the "difninitive" record of the number of sources

            check results against cm, but be aware that 
        """
        query_url = self.url % '*'
        xml = self.get(query_url, 'xml')
        nodes, lit = self.xpath(xml, '//results/result', '//literatureSummary/@resultCount')  # FIXME these queries do need to go up top to make it easier to track and modify them as needed

        nifid_count_total, resource_data_dict = self._walk_nodes(nodes, 'db', 'indexable')

        resource_data_dict[LITERATURE_ID] = ('Literature', 'Literature')
        nifid_count_total[LITERATURE_ID] = int(lit[0])

        # TODO once this source data has been retrieved we should really go ahead and make sure the database is up to date
        return resource_data_dict, nifid_count_total

    def get_counts(self, term):  #FIXME this really needs to be async or something
        """
            given a term return a dict of counts for each unique src_nifid

            IDS ARE NOT HANDLED HERE
            TERM MUNGING NOT HERE EITHER
        """
        if ' '  in term:  # we need to do this here, users shouldn't see this
            term = '"%s"' % term
        query_url = self.url % term  # any preprocessing of the term BEFORE here

        print('summary query url:', query_url)
        xml = self.get(query_url, 'xml')
        nodes, name, lit = self.xpath(xml, '//results/result', '//clauses/query',
                                      '//literatureSummary/@resultCount')

        #FIXME do we even need name anymore if we aren't dealing with ids in here?
        #TODO deal with names and empty nodes

        #FIXME this fails when there is a space because it applies AND instead of quoting
        name = name[0].text # return EXACT queries that were used
        if name != term:
            print('for some reason name != term: %s != %s'%(name, term))
            #raise TypeError('for some reason name != term: %s != %s'%(name, term))

        nifid_count = self._walk_nodes(nodes)
        #print("nifid_count", nifid_count)
        nifid_count[LITERATURE_ID] = int(lit[0])

        return nifid_count


###
#   Map terms to ids  FIXME we need some way to resolve multiple mappings to ids ;_;
###

class term_service(rest_service):  # FURL PLS
    """ let us try this with json: result--works pretty well """
    url = SCIGRAPH + "/scigraph/vocabulary/term/%s.json?limit=20&searchSynonyms=true&searchAbbreviations=false&searchAcronyms=false"
    name_url = SCIGRAPH + "/scigraph/vocabulary/id/%s.json?limit=20&searchSynonyms=true&searchAbbreviations=false&searchAcronyms=false"
    _timeout = 2

    def terms_preprocessing(self, terms):

        assert type(terms[0]) == str, "terms[0] has wrong type: %s" % terms
        # TODO do we want to deal with id/term overlap? (NO)
        terms = tuple(set([TOTAL_TERM_ID]+list(terms)))  #removes dupes

        cleaned_terms = []
        for term in terms:
            term = term.strip().rstrip().strip('"').strip().rstrip()  # insurance
            cleaned_terms.append(term)

        return cleaned_terms

    def terms_id_expansion(self, terms):
        """
            TODO we do need to map lists of terms to identifiers so that we can
            do sorting and clustering, need to work out how we will do this and
            when we will do this. We probably need 3 things:
            1) the term the user entered
            2) the id if it exists, None if we don't find a match
            3) the label for that id
        """
        # try to expand terms to identifiers
        # if that fails try to expand identifiers to terms
        # guess agressively that terms with '_' in them are identifiers
        # same goes for things that look like curies

    def get_id(self, term):
        #term = term.replace(' ','%20')  # FIXME
        query_url = self.url % term
        try:
            records = self.get(query_url, 'json')['concepts']
        except ConnectionError:
            print(query_url)
            return None
        if len(records) == 1:
            return records[0]['fragment']
        else:
            return records

    def get_iri(self, tid):
        query_url = self.name_url % tid
        try:
            records = self.get(query_url, 'json')['concepts']
        except ConnectionError:
            print(query_url)
            return None
        return records[0]['uri']

    def get_name(self, tid):
        query_url = self.name_url % tid
        try:
            records = self.get(query_url, 'json')['concepts']  # NOTE: can reveal SciGraph bugs!
        except ConnectionError:
            print(query_url)
            return None
        if len(records) != 1:
            # we probably encountered a term being used as an id :/
            #raise BaseException('what is this i dont even')
            return tid
        else:
            return records[0]['labels']

    def get_id_record(self, tid):
        query_url = self.name_url % tid
        try:
            records = self.get(query_url, 'json')['concepts']
        except ConnectionError:
            print(query_url)
            return None
        return records

    def get_term_record(self, term):
        query_url = self.url % term
        try:
            records = self.get(query_url, 'json')['concepts']
        except ConnectionError:
            print(query_url)
            return None
        return records




###
#   Ontology services
###

class ontology_service(rest_service):
    url = SCIGRAPH + "/scigraph/graph/neighbors/%s.json?depth=10&blankNodes=false&relationshipType=%s&direction=INCOMING"
    _timeout = 10
    def get_terms(self, term_id, relationship):
        query_url = self.url % (term_id, relationship)
        records = self.get(query_url, 'json')
        names = []
        for rec in records['edges']:
            if term_id in rec.values():
                for node in records['nodes']:
                    if node['id'] == rec['sub']:
                        names.append(node['lbl'])

        #FIXME the test on part of produces utter madness, tree is not clean
        return records, names

    def order_nifids(self, nifids, rule):  # TODO
        """ given a set of nifids use some rule to order them

            also needs to handle a mixture of terms and nifids

            and stick everything that can't be ordered into its own group
        """

        # note that the "rule" is almost certainly going to be some dsl ;_;
        # or I'm just going to implement a bunch of precanned ways to order stuff
        # and then the rule would just be a string mapped to a function 

        # XXX ANOTHER NOTE: given a set of terms, use the ontology to expand
        # to similar terms by traversing back up to common nodes and then
        # back down, the problem of course is all the relationships in UBERON
        # are now dirty >_< (and synonyms suck)

###
#   Stick the collected data in a datastore (postgres)
###

#table 
class database_service:  # FIXME reimplement with asyncio?
    """ This should sort of be the central hub for fielding io for the database
        it should work for caching for the phenogrid output and for csv output
    """
    dbname = ""
    user = ""
    host = "localhost"#"postgres-stage@neuinfo.org"
    port = 5432
    DEBUG = True
    def __init__(self):
        self.conn = pg.connect(dbname=self.dbname, user=self.user, host=self.host, port=self.port)
        pg.extras.register_hstore(self.conn, globally=True)
    def __enter__(self):
        pass
    def __exit__(self, type_, value, traceback):
        self.conn.close()

    def mogrify(self, *args, **kwargs):
        cur = self.conn.cursor()
        try:
            return cur.mogrify(*args, **kwargs)
        except:
            raise
        finally:
            cur.close()

        return 
    
    @sanitize_input
    def cursor_exec(self, SQL, args=None):
        cur = self.conn.cursor()
        if args:
            cur.execute(SQL, args)
        else:
            cur.execute(SQL)
        try:
            tups = cur.fetchall()
            return tups
        except pg.ProgrammingError:
            return None
        finally:
            cur.close()


class heatmap_service(database_service):
    """ The monolithic heatmap service that keeps a cache of the term counts
        as well as term names and resource names/indexable status

        for the most part it is a lightweight wrapper on top of the summary
        service but it also manages the provenance for each heatmap generated
        and can retrieve specific heatmaps by id or date
    """
    if environ.get('HEATMAP_PROD',None):  # set in heatmaps.wsgi
        dbname = "heatmap"
        host = "postgres.neuinfo.org"  # should probably put this in environment variables as well 
    else:
        dbname = "heatmap_test"
        host = "localhost"#"postgres-stage@neuinfo.org"
    user = "heatmapuser"
    port = 5432
    TERM_MIN = 5
    supported_filetypes = None, 'csv', 'json'
    def __init__(self, summary_server, term_server):
        super().__init__()
        self.summary_server = summary_server
        self.term_server = term_server
        self.term_count_dict = {TOTAL_TERM_ID:{}}  # makes init play nice
        self.term_names = {TOTAL_TERM_ID:TOTAL_TERM_ID_NAME}  #FIXME these dicts may need to be ordered so we don't use too much memory
        self.resources = None
        self.check_counts()
        output_map = {
            'json':self.output_json,
            'csv':self.output_csv,
                     }

    def check_counts(self):
        """ validate that we have the latest, if we do great
            otherwise flag all existing terms as dirty
        """
        resources, nifid_count_total = self.summary_server.get_sources()
        if len(nifid_count_total) != len(self.term_count_dict[TOTAL_TERM_ID]):
            # the total number of sources has changed!
            self.resources = resources
            self.term_count_dict = {}  # reset the cache since new source
            self.term_count_dict[TOTAL_TERM_ID] = nifid_count_total
            print("CACHE DIRTY")
        else:  # check for changes in values
            for nifid, old_value in self.term_count_dict[TOTAL_TERM_ID].items():
                if nifid_count_total[nifid] != old_value:
                    self.term_count_dict = {}
                    self.term_count_dict[TOTAL_TERM_ID] = nifid_count_total
                    print("CACHE DIRTY")
                    break  # we already found a difference

    @sanitize_input
    def get_heatmap_data_from_id(self, hm_id):  # TODO timestampt
        sql = """SELECT th.term, th.term_counts FROM heatmap_prov_to_term_history AS junc
                JOIN heatmap_prov AS hp ON hp.id=junc.heatmap_prov_id
                JOIN term_history AS th ON th.id=junc.term_history_id
                WHERE hp.id=%s;"""
        args = (hm_id,)
        tuples = self.cursor_exec(sql, args)
        if tuples:
            hm_data = {term:int_cast(nifid_count) for term, nifid_count in tuples}
            return hm_data
        else:
            return None # no id was found

    def gen_hm_data_id(self, hm_id):
        sql = """SELECT th.term, th.term_counts FROM heatmap_prov_to_term_history AS junc
                JOIN heatmap_prov AS hp ON hp.id=junc.heatmap_prov_id
                JOIN term_history AS th ON th.id=junc.term_history_id
                WHERE hp.id=%s;"""
        args = (hm_id,)
        #yield from self.cursor_exec(sql, args)

    @sanitize_input
    def get_heatmap_from_id(self, hm_id, term_id_order=None, src_id_order=None, output='json'):
        """ return default (alpha) ordereded heatmap or apply input orders
        """
        hm_data = self.get_heatmap_data_from_id(hm_id)
        if not term_id_order:
            term_id_order = sorted(hm_data) 
        if not src_id_order:
            src_id_order = sorted(hm_data[TOTAL_TERM_ID])
        heatmap = dict_to_matrix(hm_data, term_id_order, src_id_order)

    @sanitize_input
    def get_timestamp_from_id(self, hm_id):
        sql = """SELECT datetime FROM heatmap_prov WHERE id=%s;"""
        args = (hm_id,)
        tuples = self.cursor_exec(sql, args)
        if tuples:
            timestamp = tuples[0][0].isoformat()
            return timestamp
        else:
            return None

    def get_term_counts(self, *terms):  #FIXME this fails if given an id!
        """ given a collection of terms returns a dict of dicts of their counts
            this is where we make calls to summary_server, we are currently handling
            term failures in here which seems to make sense for time efficiency
        """
        cleaned_terms = self.term_server.terms_preprocessing(terms)  # clean terms
        terms = None  # insurance against stupidity
        term_count_dict = {}
        failed_terms = []
        for term in cleaned_terms:
            try:
                nifid_count = self.term_count_dict[term]
            except KeyError:
                print(term)
                try:  # FIXME :/
                    nifid_count = self.summary_server.get_counts(term)
                    self.term_count_dict[term] = nifid_count
                except requests.exceptions.ReadTimeout:
                    failed_terms.append(term)
                    continue  # drop the term from the results

            term_count_dict[term] = nifid_count

        if failed_terms: print("Failed terms: ", failed_terms)
        return term_count_dict, failed_terms

    def get_terms_from_ontology(self, term):
        """  TODO somehow this seems like it should be able to take a more
            complex query or something... 

            also not clear if we actually want to hand this in THIS class
            or if we want to put this code in the ontology server or something
            
            same issue with the orders, the order service should probably stay
            with the ontology server
        """

    def get_names_from_ids(self, id_order):
        """ consistent way to get the names for term or src ids
            we do it this way because we only stick the names on
            at the end after everything else is done being orderd
        """
        # src names from self.resources
        # term names from... self.term_server?? term keys will be a mix of names and ids
            #we can run stats on term id coverage in the ontology
        try:
            name_order = []
            for src_id in id_order:
                name = ' '.join(self.resources[src_id])  # get name for each view
                name_order.append(name)
        except KeyError:  # it's terms
            name_order = []  # just in case something wonky happens up there
            for term_id in id_order:
                name = self.term_server.get_name(term_id)  #FIXME we should keep a cache of this
                if name:
                    name_order.append(name)
                else:  # term_id isnt a term_id, so probably already a name
                    name_order.append(term_id)

        return name_order

    @sanitize_input
    def make_heatmap_data(self, *terms):  # FIXME error handling
        """ this call mints a heatmap and creates the prov record
            this is also where we will check to see if everything is up to date
        """
        self.check_counts() #call to * to validate counts
        hm_data, fails = self.get_term_counts(*terms)  # call this internally to avoid race conds
        
        terms = tuple(hm_data)  # prevent stupidity with missing TOTAL_TERM_ID

        if len(terms) < self.TERM_MIN:  #TODO need to pass error back out for the web
            message = "We do not mint DOIS for heatmaps with less than %s terms."%self.TERM_MIN
            print(message)
            return hm_data, None, message

        #check if we already have matching data in term_history
            #if we have matching data record the
                #XXX history id
            #if we dont have matching data record create the
                #XXX history id
        sql_check_terms = """SELECT id, term, term_counts FROM term_history
                            WHERE id = (SELECT MAX(id) FROM term_history AS
                            th WHERE th.term=term_history.term) AND term IN %s;
                            """ # only check the latest record
        args = (terms,)
        check_result = self.cursor_exec(sql_check_terms, args)
        newest_term_counts = {term:(th_id, int_cast(nifid_count)) for
                              th_id, term, nifid_count in check_result}

        sql_ins_term = "INSERT INTO term_history (term, term_counts) VALUES(%s,%s) RETURNING id;"
        th_ids = []
        for term, new_nifid_count in hm_data.items():  # validate terms counts
            try:
                th_id, old_nifid_count = newest_term_counts[term]
                old_nifid_count = int_cast(old_nifid_count)
            except KeyError:
                old_nifid_count = None

            if new_nifid_count != old_nifid_count:  # we cant reuse counts
                ins_args = (term, str_cast(hm_data[term]))
                ti_result = self.cursor_exec(sql_ins_term, ins_args)
                th_id = ti_result[0][0]

            th_ids.append(th_id)

        if len(th_ids) == len(terms):  #all terms identical get existing id
            sql_hp_ids = ("SELECT DISTINCT heatmap_prov_id FROM"
            " heatmap_prov_to_term_history WHERE term_history_id IN %s")
            sql = ("SELECT DISTINCT heatmap_prov_id, term_history_id FROM"
            " heatmap_prov_to_term_history WHERE term_history_id IN %s")
            args = (tuple(th_ids),)
            existing_hm_ids = self.cursor_exec(sql_hp_ids, args)
            existing_th_ids = self.cursor_exec(sql, args)

            # we need hit the newest hm_ids first in case 
            for (existing_hm_id,) in existing_hm_ids:
                old_th_ids = [ti for hi, ti in existing_th_ids if hi == existing_hm_id]
                if set(th_ids) == set(old_th_ids): #rows exist under a SINGLE heatmap
                    sql = "SELECT DateTime FROM heatmap_prov WHERE id=%s" 
                    args = (existing_hm_id,)
                    timestamp = self.cursor_exec(sql, args)
                    return hm_data, existing_hm_id, timestamp

        #create a new record in heatmap_prov since we didn't find an existing record
            #reccomend that users request the terms they need a single time for download
            #OR we just rate limit the number of heatmaps that can be requested XXX <-this
            #create the record
        sql_hp = "INSERT INTO heatmap_prov DEFAULT VALUES RETURNING id, DateTime"  # just use the primary key in the url
        print(sql_hp)
        [(hp_id, timestamp)] = self.cursor_exec(sql_hp)
        #hp_id = hp_result[0][0]

        #insert into heatmap_prov_to_term_history
            #XXX prov id #XXX history id pairs
        sql_add_junc = b"INSERT INTO heatmap_prov_to_term_history VALUES "#(%s,%s)"
        hp_ids = [hp_id] * len(th_ids)
        junc_args = (hp_ids, th_ids)
        sql_values = b",".join(self.mogrify("(%s,%s)", tup) for tup in zip(*junc_args))
        self.cursor_exec(sql_add_junc + sql_values)

        #commit it (probably wrap this in a try/except)
        self.conn.commit()

        return hm_data, hp_id, timestamp

    def output_csv(self, heatmap_data, term_id_order, src_id_order, sep=",", export_ids=True):
        """ consturct a csv file on the fly for download response """
        #this needs access id->name mappings
        #pretty sure I already have this written?
        matrix = dict_to_matrix(heatmap_data, term_id_order, src_id_order)
        term_names = ['"%s"' % n if sep in n else n for n in self.get_names_from_ids(term_id_order)]
        src_names = ['"%s"' % n if sep in n else n for n in self.get_names_from_ids(src_id_order)]
        term_id_order = ['"%s"' % n if sep in n else n for n in term_id_order]  # deal with commas in names
        src_id_order = ['"%s"' % n if sep in n else n for n in src_id_order]  # probably dont need this here

        if export_ids:
            empty_col_str = sep * 2
        else:
            empty_col_str = sep * 1

        csv_string = ""
        csv_string += empty_col_str + sep.join(src_names) + "\n"
        if export_ids:
            csv_string += empty_col_str + sep.join(src_id_order) + "\n"

        if export_ids:
            for term_name, term_id, row in zip(term_names, term_id_order, matrix):
                line = term_name + sep + term_id + sep + sep.join(str(i) for i in row) + "\n"
                csv_string += line
        else:
            for term_name, row in zip(term_names, matrix):
                line = term_name + sep + sep.join(str(i) for i in row) + "\n"
                csv_string += line

        return csv_string

    def output_json(self, heatmap_data):
        """ return a json object with the raw data and the src_id and term_id mappings """
        return simplejson.dumps(heatmap_data)

    def output_png(self, heatmap_data, termSort, sourceSort, termCollapse, sourceCollapse):
        return "THIS IS A PNG FILE I SWEAR" 

    def __repr__(self):
        a = str(self.resources).replace('),','),\n')+'\n'
        b = repr(self.term_count_dict).replace(',',',\n')
        return 

###
#   utility functions  FIXME these should probably go elsewhere?
###

        

def f(*args, **kwargs):
    print("Take a peek at what this thing looks like.")
    embed()
    raise NotImplementedError("Please implement me so I can become a real function ;_;")

#FIXME is it possible to write a psycopg2 type cast to avoid this?
def int_cast(dict):
    return {k:int(v) for k,v in dict.items()}
def str_cast(dict):
    return {k:str(v) for k,v in dict.items()}

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
            ordered.append(None)  # convert to zero later for numerical
    return  ordered
                        
def dict_to_matrix(tdict_sdict, term_id_order, src_id_order):
    """ given heatmap data, and orders on sources and terms
        return a matrix representation
    """
    #sanity check
    if len(tdict_sdict) < len(term_id_order):  # term_ids can be a subset!
        # note that we *could* allow empty terms in the dict but that should
        # be handled elsewhere
        embed()
        raise IndexError("Term orders must be subsets of the dict!")
    if len(tdict_sdict[TOTAL_TERM_ID]) != len(src_id_order):  # these must match
        raise IndexError("Source orders must match the total source counts!")

    matrix = np.empty((len(term_id_order), len(src_id_order)))
    for i, term in enumerate(term_id_order):
        row = apply_order(tdict_sdict[term], src_id_order)
        matrix[i,:] = row

    return np.nan_to_num(matrix)


###
#   main
###


def main():
    ts = term_service()
    ss = summary_service()
    os = ontology_service()
    t = "UBERON_0000955"  # FIXME a reminder that these ontologies do not obey tree likeness and make everything deeply, deeply painful
    r = "BFO_0000050"
    j = os.get_terms(t, r)


if __name__ == '__main__':
    main()
