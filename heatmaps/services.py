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

if environ.get('HEATMAP_PROD',None):  # set in heatmaps.wsgi if not globally
    embed = lambda args: print("THIS IS PRODUCTION AND PRODUCTION DOESNT LIKE IPYTHON ;_;")
else:
    from IPython import embed

from .visualization import applyCollapse, dict_to_matrix, sCollapseToSrcId, make_png
from .scigraph_client import Graph, Vocabulary

# initilaize scigraph services
graph = Graph()
vocab = Vocabulary()

"""
INSERT INTO view_history (id, source_id_order, term_counts) VALUES (
1,
'{"a", "b", "c"}',
'brain => "[1 2 3 4]"'
);

SELECT * FROM view_sources LEFT OUTER JOIN source_entity ON REPLACE(view_sources.src_nif_id,'_','-')=source_entity.nif_id;

SELECT nif_id FROM relation_entity WHERE is_view=TRUE; --burak has a service for this
"""

# sql to update from NULL termcounts to, with an extra check to make sure we never overwrite accidentally
"""
UPDATE term_history SET term_counts=%s WHERE id=%s and term_counts IS NULL;
"""

# sql to retrieve unfinished term counts
"""
SELECT * FROM term_history WHERE term_counts IS NULL;
"""
# sql to get terms that have finished all terms but have not set a finished date TODO trigger?
# FIXME will not work as desired :/
# FIXME argh what do we do when we already have an existing identical heatmap!? well... we have no new rows...
# I supposed we could insert an equivalence, but we can't insert all the new terms at the same time... and leave them null
# we would create loads of duplicates, we also don't want to add a row to the junction table 
# TODO we will add a new heatmap ID so we can give users a link, we will then run as we currently do and if we find existing
# terms that have not changed we will add those rows to the junction table...
# if cache isn't dirty... get all the latest entries and check... we do this... if the cache IS dirty
# go ahead and create a new heatmap prov id and then update or use the latest values from the database
# HRM in this case we don't even have to hit the database we just can just call it 'old cache' and add a field
# that has the identifier for the most recent occurence of that term (which we will need to add when we go to the database)
"""
SELECT DISTINCT(hp.id) FROM heatmap_prov_to_term_history AS junc
JOIN heatmap_prov AS hp ON hp.id=junc.heatmap_prov_id
JOIN term_history AS th ON th.id=junc.term_history_id
WHERE hp.done_datetime IS NULL AND th.term_counts IS NOT NULL;
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
    old_url = "http://nif-services.neuinfo.org/servicesv1/v1/summary.xml?q=%s"
    url = "http://beta.neuinfo.org/services/v1/summary.xml?q=%s"
    _timeout = 20

    missing_ids = 'nif-0000-21197-1', 'nif-0000-00053-2'
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

        # For compatibility we include the 'old' data as well since stuff doesn't overlap :/
        # man I hope we never get rid of a view :/
        old_query_url = self.old_url % '*'
        old_xml = self.get(old_query_url, 'xml')
        old_nodes, old_lit = self.xpath(old_xml, '//results/result', '//literatureSummary/@resultCount')  # FIXME these queries do need to go up top to make it easier to track and modify them as needed
        old_nifid_count_total, old_resource_data_dict = self._walk_nodes(old_nodes, 'db', 'indexable')
        resource_data_dict.update(old_resource_data_dict)  # URG

        # TODO once this source data has been retrieved we should really go ahead and make sure the database is up to date
        return resource_data_dict, nifid_count_total

    def get_counts(self, term):  #FIXME this really needs to be async or something
        # FIXME we need anaomoly detection here! if we are suddenly getting back no results!
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

        #TODO we need to gather all the metadata about the expansion used

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

class term_service():  # FURL PLS

    def __init__(self):
        self.known_curies = vocab.getCuriePrefixes()

    def terms_preprocessing(self, terms):

        assert type(terms[0]) == str, "terms[0] has wrong type: %s" % terms
        # TODO do we want to deal with id/term overlap? (NO)
        terms = tuple(set([TOTAL_TERM_ID]+list(terms)))  #removes dupes

        cleaned_terms = []
        for term in terms:
            term = term.strip().rstrip().strip('"').strip().rstrip()  # insurance
            cleaned_terms.append(term)

        return cleaned_terms

    def get_equiv_classes(self, curie):
        json = graph.getNeighbors(curie, relationshipType='equivalentClass')
        if not json:
            return (curie,), (curie,)

        syns = set()
        curies = set()

        for node in json['nodes']:
            curies.add(node['id'])
            syns.add(node['lbl'])
            if 'synonym' in node['meta']:
                syns.update(node['meta']['synonym'])  # FIXME lower()?

        output = tuple(sorted(curies)), tuple(syns)  # sort for crossrun const
        return output

    def pick_identifier(self, term, record_list):
        """
            give a score to each potential identifier
            return the identifiers of all equivalent classes
            of the curie with the highest score
            if there is more than one record at a given score level
            rank the subrecords and return the identifiers of all
            equivalent classes of the curie with the highest score
        """
        scores = [[], [], [], [], []]
        for record in record_list:
            label = record['labels'][0]
            syns = record['synonyms']
            if term == label:
                scores[0].append(record)
            elif term.lower() == label.lower():
                scores[1].append(record)
            elif term in syns:
                scores[2].append(record)
            elif term.lower() in [s.lower() for s in syns]:
                scores[3].append(record)
            else:
                continue

        # equivalent class assertions check?

        record = None
        for score, records in enumerate(scores):
            if records:
                print('record found at score', score)
                if len(records) == 1:
                    record = records[0]
                    curie = record['curie']
                    new_cs, new_syns = self.get_equiv_classes(curie)
                    return new_cs, new_syns, (record['curie'], record['labels'][0])
                else:  # CURIE preference ordering if there are multiples at the same lvl
                    # cscore will be by max number of matching equiv curies (min is 1)
                    # that is 1 then we fail over to total equiv curies
                    # then number of syns
                    # all else fails we go alpha on the curie
                    curies = [r['curie'] for r in records]
                    #"""
                    # careful with curies that are None, need to fix that in nifstd :/
                    curies_labels = [t for t in sorted([(r['curie'], r['labels'][0])
                                                        for r in records if r['curie'] is not None])]
                    """  # if you need this code you are probably missing a curie somewhere
                    for r in records:
                        c = r['curie']
                        l = r['labels'][0]
                        if c is None or l is None:
                            embed()

                    curies_labels = [t for t in sorted([(r['curie'] if r['curie'] else '###### WTF M8',
                                                         r['labels'][0] if r['labels'][0] else '###### WTF M8') for r in records])]
                    #"""
                    output_curies = None
                    output_syns = None
                    oc = None
                    ol = None

                    s_total_match = 0
                    s_total_equiv = 0
                    s_total_syns = 0
                    for c, l in curies_labels:
                        new_cs, new_syns = self.get_equiv_classes(c)
                        if new_cs == curies:  # they're all equivalent classes
                            oc, ol = c, l
                            print('ALL SYNONYMS CASE')
                            return new_cs, new_syns, (oc, ol)

                        match = len(set(new_cs).intersection(set(curies)))

                        if match > s_total_match:
                            output_curies = new_cs
                            output_syns = new_syns
                            oc, ol = c, l
                            s_total_match = match
                            s_total_equiv = len(new_cs)
                            s_total_syns = len(new_syns)
                        elif match == s_total_match:
                            if len(new_cs) > s_total_equiv:
                                output_curies = new_cs
                                output_syns = new_syns
                                oc, ol = c, l
                                s_total_equiv = len(new_cs)
                                s_total_syns = len(new_syns)
                            elif len(new_cs) == s_total_equiv:
                                if len(new_syns) > s_total_syns:
                                    output_curies = new_cs
                                    output_syns = new_syns
                                    oc, ol = c, l
                                    s_total_syns = len(new_syns)
                                else:
                                    pass  # already sorted alphabetically

                    return output_curies, output_syns, (oc, ol)

        return (), (term,), (None, None)  # all fail terms are own syns

    def term_id_expansion(self, putative_term):  # FIXME NOT deterministic wrt changes in scigraph
        # TODO do we need to store raw term -> id mappings?! we want to collect terms that have no hits
        # but if we just store the raw query term in the database then 
        # this approach also means that stuff can get out of sync w/ the nif results
        # we REALLY do not want to store the full expanded query (with ands etc that we use for each term
        # maybe we can return all the expansions we are going to use on the first page and then
        # have that page with an OK button to actually build the heatmap... yes... this seems good
        """
            We do all expansions here internally to keep things in sync
            the summary service should never see a raw identifier if it exists
            in scigraph.

            TODO we do need to map lists of terms to identifiers so that we can
            do sorting and clustering, need to work out how we will do this and
            when we will do this. We probably need 3 things:
            1) the term the user entered
            2) the id if it exists, None if we don't find a match
            3) the label for that id
            4) synonyms (no acronyms or abbrevs for now)

            return the exact query string to run on services
        """
        if type(putative_term) is not str:
            raise TypeError('putative term is not a string! %s' % str(putative_term))

        # curie or fragment
        if putative_term.split(':')[0] in self.known_curies or putative_term.split('_')[0] in self.known_curies:
            curie = putative_term.replace('_', ':')
            # this sucks esp hard when we have birnlex_xxxxxxx prefixed identifiers used with
            # 20 different iri prefixes :/
            record_list = vocab.findById(curie)  # assume its a curie and try
            if type(record_list) is dict:  # heh, stupid hack
                record_list = [record_list]
        else:
            curie = None
            record_list = vocab.findByTerm(putative_term)

        if record_list:  # it is a curie
            if curie is not None:
                if len(record_list) == 1:
                    record = record_list[0]
                    curie = record['curie']
                    label = record['labels'][0]
                    if curie != putative_term.replace('_',':'):  # matches both _ and : versions
                        raise TypeError('%s != %s' % (curie, putative_term))
                    curies, syns = self.get_equiv_classes(curie)
                else:
                    embed()
                    raise TypeError('WAT')
            else:  # we're going to treat it like a term
                curies, syns, (curie, label) = self.pick_identifier(putative_term, record_list)
        else:
            curie = None
            label = None
            syns = (putative_term,)

        # check if it is a term, a fragment, or a curie
        # try to expand terms to identifiers
        # if that fails try to expand identifiers to terms
        # guess agressively that terms with '_' in them are identifiers
        # same goes for things that look like curies

        query = ' AND '.join(syns)

        return putative_term, curie, label, query

    def get_name(self, tid):
        # try to convert fragments into CURIE form
        tid = tid.replace('_',':')  # FIXME this will only work SOMETIMES
        json = vocab.findById(tid)  # FIXME cache this stuff?
        return json['labels'][0] if json else None

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


class heatmap_service(database_service):  # FIXME YEP ITS BLOCKING DEERRRPPPP
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
    supported_filetypes = None, 'csv', 'json', 'png'
    mimetypes = {None:'text/plain',
                 'csv':'text/csv',
                 'json':'application/json',
                 'png':'image/png'}
    supported_termSort = 'alpha_id', 'alpha_name', 'original', 'uploaded', 'identifier', 'frequency', 'literature'
    supported_sourceSort = 'alpha_id', 'alpha_name', 'uploaded', 'identifier', 'frequency'

    def __init__(self, summary_server, term_server):
        super().__init__()
        self.summary_server = summary_server
        self.term_server = term_server
        self.term_count_dict = {TOTAL_TERM_ID:{}}  # makes init play nice
        self.term_names = {TOTAL_TERM_ID:TOTAL_TERM_ID_NAME}  #FIXME these dicts may need to be ordered so we don't use too much memory
        self.heatmap_term_order = {}  # temp store of the original order
        self.resources = None
        self.check_counts()
        self.output_map = {
            None:self.output_json,
            'json':self.output_json,
            'csv':self.output_csv,
            'png':self.output_png,
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
        heatmap = dict_to_matrix(hm_data, term_id_order, src_id_order, TOTAL_TERM_ID)

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

    def get_name_from_id(self, id_):
        if id_ in self.resources:
            return self.resources[id_]
        else:  # it's a term!
            if id_ not in self.term_names:
                name = self.term_server.get_name(id_)
                if name:
                    self.term_names[id_] = name
                    return name
                else:
                    return id_
            else:
                name = self.term_names[id_]
                return name

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
                if term_id not in self.term_names:
                    name = self.term_server.get_name(term_id)  #FIXME we should keep a cache of this
                    if name:
                        self.term_names[term_id] = name  # FIXME??!? add none even if none?
                else:
                    name = self.term_names[term_id]

                if name:
                    name_order.append(name)
                else:  # term_id isnt a term_id, so probably already a name
                    name_order.append(term_id)

        return name_order

    @sanitize_input
    def make_heatmap_data(self, *terms):  # FIXME error handling
        # SUEPER DUPER FIXME this has to be converted to async :/ preferably in webapp.py
        # FIXME FIXME, caching and detection of existing heatmaps is BROKEN
        # 1) we invalidate caches incorrectly and we can be fooled by a cached
        # result on the summary service itself, we also need to check at least a
        # single term to see if it matches, doing a full resync sucks but if we
        # don't have a cache.... eh... not really a big deal with making new copies
        # of the same data, bigger problem is if we can't update a bad heatmap because
        # the federation_totals haven't changed but the results for terms themsevles have
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
        
        #store the original order of the terms in memory for now, maybe allow reup later w/ specific orders from elsewhere
        self.heatmap_term_order[hp_id] = terms

        return hm_data, hp_id, timestamp

    def output_csv(self, matrix, term_name_order, src_name_order, term_id_order,
                   src_id_order, *args, sep=",", export_ids=True, **kwargs):
        """ consturct a csv file on the fly for download response """
        #this needs access id->name mappings
        #pretty sure I already have this written?
        #matrix = dict_to_matrix(heatmap_data, term_id_order, src_id_order, TOTAL_TERM_ID)
        term_names = ['"%s"' % n if sep in n else n for n in term_name_order]
        src_names = ['"%s"' % n if sep in n else n for n in src_name_order]
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

        return csv_string, self.mimetypes['csv']

    def output_json(self, heatmap_data, *args, **kwargs):
        """ return a json object with the raw data and the src_id and term_id mappings """
        return simplejson.dumps(heatmap_data), self.mimetypes['json']

    def output_png(self, matrix, term_name_order, src_name_order, *args, title='heatmap', **kwargs):
        limit = 900
        if len(matrix) > 900:
            return "There are too many terms to render as a png. Limit is %s." % limit, self.mimetypes[None]
        row_names = term_name_order
        col_names = src_name_order
        png = make_png(matrix, row_names, col_names, title)
        return png, self.mimetypes['png']

    def output(self, heatmap_id, filetype, sortTerms=None, sortSources=None,
               collTerms=None, collSources=None, idSortTerms=None, idSortSources=None,
               ascTerms=True, ascSources=True):
        """
            Provide a single API for all output types.
        """
        if filetype not in self.output_map:
            return None, "Unsupportred filetype!"
        else:
            output_function = self.output_map[filetype]

        heatmap_data = self.get_heatmap_data_from_id(heatmap_id)
        if not heatmap_data:
            return None, "No heatmap with that ID!", None

        timestamp = self.get_timestamp_from_id(heatmap_id)  # FIXME start/done timestamp? no answer to the yet :/
        timestamp = timestamp.replace(':','_')  # for consistency wrt attachment;
        filename = 'nif_heatmap_%s_%s.%s' % (heatmap_id, timestamp, filetype)

        #if filetype == 'json':  # FIXME FIXME FIXME ARGH well... it is the only unsorted type
            #representation, mimetype = output_function(heatmap_data)
            #return representation, filename, mimetype

        # collapse rules and execution (need to go in their own function)
        # terms
        if collTerms == 'cheese':
            term_coll_function = lambda heatmap_data, term_id_name_dict: heatmap_data, term_id_name_dict
            term_id_name_dict = {id_:self.get_name_from_id(id_) for id_ in heatmap_data}
        else:
            term_coll_function = None
            term_id_name_dict = {id_:self.get_name_from_id(id_) for id_ in heatmap_data}

        if term_coll_function:
            term_id_coll_dict, term_id_name_dict = term_coll_function(heatmap_data, term_id_name_dict)
        else:
            term_id_coll_dict = None

        # sources
        if collSources == 'cheese':
            src_coll_function = lambda heatmap_data_ttid, src_id_name_dict: heatmap_data_ttid, src_id_name_dict
            src_id_name_dict = {id_:self.get_name_from_id(id_) for id_ in heatmap_data[TOTAL_TERM_ID]}
        elif collSources == 'collapse views to sources':
            src_coll_function = sCollapseToSrcId
            src_id_name_dict = {id_:name_tup[0] for id_, name_tup in self.resources.items()}
        else:
            src_coll_function = None
            src_id_name_dict = {id_:' '.join(self.get_name_from_id(id_)) for id_ in heatmap_data[TOTAL_TERM_ID]}

        if src_coll_function:
            src_id_coll_dict, src_id_name_dict = src_coll_function(heatmap_data[TOTAL_TERM_ID], src_id_name_dict)
        else:
            src_id_coll_dict = None

        # apply the collapse dicts to the data, need to do before sorting for some sort options
        if term_id_coll_dict:
            heatmap_data = applyCollapse(heatmap_data, term_id_coll_dict, term_axis=True)

        if src_id_coll_dict:
            heatmap_data = applyCollapse(heatmap_data, src_id_coll_dict)

        # sort options are drawn from this class and do not accept arbitrary input
        # TODO this needs to go in its own method

        ascTerms = 1 if ascTerms else -1
        ascSources = 1 if ascSources else -1
        if sortTerms == 'original':
            term_id_sort = sorted
            if heatmap_id in self.heatmap_term_order:  # FIXME mutex with term collapse
                orig_order = self.heatmap_term_order[heatmap_id]
                term_id_key = lambda x: orig_order.index(x[0])
            else:
                print('Original failed using alpha for terms for heatmap', heatmap_id)
                term_id_key = lambda x: x[1]  # FIXME nasty nasty hidden hack
                #return None, 'Original order no longer on the server :(', None
        elif sortTerms == 'alpha_id':
            term_id_sort = sorted
            term_id_key = lambda x: x[0]
        elif sortTerms == 'alpha_name':
            term_id_sort = sorted
            term_id_key = lambda x: x[1]
        elif sortTerms == 'literature':
            # sort by number of literature results
            term_id_sort = sorted
            term_id_key = lambda x: ascTerms * heatmap_data[x[0]].get(LITERATURE_ID, 0)
        elif sortTerms == 'identifier':
            # sort by number of results w/in a given datasources
            term_id_sort = sorted
            term_id_key = lambda x: ascTerms * heatmap_data[x[0]].get(idSortTerms, 0)
        elif sortTerms == 'frequency':
            # sort by total number of sources w/ 1 or more hits
            term_id_sort = sorted
            term_id_key = lambda x: ascTerms * len([v for v in heatmap_data[x[0]].values() if v > 0])
        else:  # FIXME we shouldn't need this
            term_id_sort = sorted
            term_id_key = lambda x: x[0]

        # sources
        if sortSources == 'alpha_id':
            src_id_sort = sorted
            src_id_key = lambda x: x[0]
        elif sortSources == 'alpha_name':
            src_id_sort = sorted
            src_id_key = lambda x: x[1]
        elif sortSources == 'frequency':
            # number terms that appear in this source NOT the sum of all counts
            src_id_sort = sorted
            src_id_key = lambda x: ascSources * len([v for v in heatmap_data.values() if x[0] in v])
        elif sortSources == 'identifier':
            # sort based on the (normalized) number of results for a given term identifier
            src_id_sort = sorted
            src_id_key = lambda x: ascSources * heatmap_data[idSortSources].get(x[0], 0) / heatmap_data[TOTAL_TERM_ID][x[0]]
        else:
            src_id_sort = sorted
            src_id_key = lambda x: x[0]

        print('sortTerms', sortTerms, 'sortSources', sortSources)

        # derive the id and name orders from the sort function
        term_id_order, term_name_order = [c for c in zip(*term_id_sort([(id_, name)
                                            for id_, name in term_id_name_dict.items()], key=term_id_key))]

        src_id_order, src_name_order = [c for c in zip(*src_id_sort([(id_, name)
                                          for id_, name in src_id_name_dict.items()], key=src_id_key))]
        # deal with dict vs matrix representation of the data
        if filetype in ('json', None):
            matrix = heatmap_data
        else:
            matrix = dict_to_matrix(heatmap_data, term_id_order, src_id_order, TOTAL_TERM_ID)

        representation, mimetype = output_function(matrix, term_name_order, src_name_order, term_id_order, src_id_order)

        return representation, filename, mimetype


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
