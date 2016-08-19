#!/usr/bin/env python3
"""
    This file contains the code that:
    1) retrieves data from the summary service on a term by term basis
    2) maintains records for common terms (cache)
    3) manages the provenance for specific heatmaps that have been saved
    4) maintains collapse maps??? or should this happen independently?
    5) calls into the ontology to traverse the graph

"""

import json
from functools import wraps
from os import environ, path
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from collections import namedtuple, defaultdict

import requests
import psycopg2 as pg
from psycopg2.extras import register_hstore

if environ.get('HEATMAP_PROD',None):  # set in heatmaps.wsgi if not globally
    embed = lambda args: print("THIS IS PRODUCTION AND PRODUCTION DOESNT LIKE IPYTHON ;_;")
else:
    from IPython import embed

from .visualization import applyCollapse, dict_to_matrix,sCollapseToSrcId, sCollapseToSrcName, make_png, sCollToLength, sCollByTermParent
from pyontutils.scigraph_client import Graph, Vocabulary
from pyontutils.hierarchies import creatTree, in_tree
from pyontutils.scigraph_client import Graph, Vocabulary

# initilaize scigraph services
graph = Graph(cache=True)
vocab = Vocabulary(cache=True)

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

# TODO logging and perf

### THINGS THAT GO ELSEWHERE
# SCIGRAPH EXPANSION DOES NOT GO HERE  #FIXME but maybe running/handling the transitive closure does?
# REST API DOES NOT GO HERE



#the number of columns IS NOT STATIC
#the ORDER of the columns in the source is also NOT STATIC
#the mapping is to identifiers
#we must use a dict/hstore and THEN map to columns

###
#   urls that may change, and identifiers that need to be defined globally
###

SCIGRAPH = "http://matrix.neuinfo.org:9000"
LITERATURE_ID = 'nlx_82958'  # FIXME pls no hardcode this (is a lie too)
TOTAL_TERM_ID = 'federation_totals'  # DO NOT CHANGE
TOTAL_TERM_ID_NAME = 'Federation Totals'

###
#   Decorators
###

def idSortSame(function):
    function.__sort_same__ = True
    return function

def idSortOther(function):
    function.__sort_other__ = True
    return function

def termsOnly(function):
    function.__terms_only__ = True
    return function

def srcsOnly(function):
    function.__srcs_only__ = True
    return function

def sanitize_input(function):
    """ Right now this is just a reminder function to flag functions that
        need to have their input sanitized since they are inserted into the sql
    """
    @wraps(function)
    def wrapped(*args, **kwargs):
        return function(*args,**kwargs)
    return wrapped

###
#   Map terms to ids  FIXME we need some way to resolve multiple mappings to ids ;_;
###

class term_service():  # FURL PLS

    def __init__(self):
        self.known_curies = vocab.getCuriePrefixes()
        self.expansion_cache = {}  # TODO see if we actually need to gc this periodically
        self.curie_map = {}  # for the time being we will construct this a term at a time

    def terms_preprocessing(self, terms):

        assert type(terms[0]) == str, "terms[0] has wrong type: %s" % terms
        # TODO do we want to deal with id/term overlap? (NO)
        terms = tuple(set([TOTAL_TERM_ID]+list(terms)))  #removes dupes

        cleaned_terms = []
        bad_terms = []
        for term in terms:
            term = term.strip().rstrip().strip('"').strip().rstrip()  # insurance
            cleaned_terms.append(term)
            if ':' in term and ' ' not in term:
                if term.split(':')[0] not in self.known_curies:
                    reason = ('Colon detected in term without a space. '
                    'Please remove the colon, it will cause a parse error')
                    bad_terms.append((term, reason))
            elif '&' in term:
                reason = ('Ampresand detect in term. '
                'Please remove the ampresand, it will cause a parse error.')
                bad_terms.append((term, reason))

        return cleaned_terms, bad_terms

    def get_fragment(self, curie):
        prefix, id_ = curie.split(':')
        if prefix not in self.known_curies:
            # this should never happen: preprocessing should have caught it
            raise TypeError('curie has unknown prefix! %s' % prefix)

        iri = self.curie_map.get(prefix, None)

        if not iri:
            iri = vocab.findById(curie)['iri'].rstrip(id_)
            self.curie_map[prefix] = iri
            #iri = record['iri'].rstrip(id_)

        if iri.endswith('#'):
            return id_

        prefrag = iri.rsplit('/',1)[-1]
        return prefrag + id_

    def get_equiv_classes(self, curie):
        if curie is None:
            raise TypeError('curie is None!')
        json = graph.getNeighbors(curie, relationshipType='equivalentClass')
        if json is None:
            return (curie,), (curie,)

        syns = set()
        curies = set()

        for node in json['nodes']:
            curies.add(node['id'])
            if node['lbl'] is not None:  # sometimes it happens! :/
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
            label = record['labels'][0] if record['labels'] else None
            syns = record['synonyms']

            if label == None:
                continue  # DO NOT WANT
            elif term == label:
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
                    if record['curie'] is not None:
                        curie = record['curie']
                        new_cs, new_syns = self.get_equiv_classes(curie)
                        return new_cs, new_syns, (curie, record['labels'][0] if record['labels'] else None)
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
                    bad_symbols = ('/','#')
                    i = 0
                    stop = len(curies_labels)
                    while i < stop:
                        for symbol in bad_symbols:
                            if symbol in curies_labels[i][0]:
                                curies_labels.append(curies_labels.pop(i))
                                stop -= 1
                                break  # inner break
                        i += 1

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

        if putative_term in self.expansion_cache:
            return self.expansion_cache[putative_term]

        # curie or fragment
        if putative_term.split(':')[0] in self.known_curies or putative_term.split('_')[0] in self.known_curies:
            # this sucks esp hard when we have birnlex_xxxxxxx prefixed identifiers used with
            # 20 different iri prefixes :/
            if ':' not in putative_term:
                curie = putative_term.replace('_', ':')
            else:
                curie = putative_term
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
                    label = record['labels'][0] if record['labels'] else None
                    if ':' not in curie and curie != putative_term.replace('_',':'):  # matches both _ and : versions
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

        #query = ' AND '.join(syns)
        output = putative_term, curie, label, syns
        self.expansion_cache[putative_term] = output
        return output

    def get_name(self, tid):
        # try to convert fragments into CURIE form
        tid = tid.replace('_',':')  # FIXME this will only work SOMETIMES
        if ' ' in tid or ':' not in tid:  # no space in ids & SG>1.5 requries cuires
            return None
        json_data = vocab.findById(tid)  # FIXME cache this stuff?
        return json_data['labels'][0] if json_data else None

TERM_SERVER = term_service()  # sillyness but nice for caching

###
#   Retrieve summary per term
###

class summary_service:  # FIXME implement as a service/coro? with asyncio?
    old_url = "http://nif-services.neuinfo.org/servicesv1/v1/summary.json?q=%s"
    url = "http://beta.neuinfo.org/services/v1/summary.json?q=%s"
    url, old_url = old_url, url
    _timeout = 60

    missing_ids = 'nif-0000-21197-1', 'nif-0000-00053-2'

    def get(self, url):
        return requests.get(url, timeout=self._timeout).json()

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
        json_data = self.get(query_url)

        datasources = json_data['result']['federationSummary']['results']
        lit_count = json_data['result']['literatureSummary']['resultCount']

        nifid_count_total = {d['nifId']:d['count'] for d in datasources}
        resource_data_dict = {d['nifId']:(d['db'], d['indexable']) for d in datasources}

        resource_data_dict[LITERATURE_ID] = ('Literature', 'Literature')
        nifid_count_total[LITERATURE_ID] = lit_count

        # For compatibility we include the 'old' data as well since stuff doesn't overlap :/
        # man I hope we never get rid of a view :/
        old_query_url = self.old_url % '*'
        old_json = self.get(old_query_url)
        old_datasources = old_json['result']['federationSummary']['results']
        old_resource_data_dict = {d['nifId']:(d['db'], d['indexable']) for d in old_datasources}

        resource_data_dict.update(old_resource_data_dict)  # make sure we have the union of all sources

        # TODO once this source data has been retrieved we should really
        # go ahead and make sure the database is up to date
        # this needs to be put elsewhere though
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
        elif ':' in term:  # this should only happen if it passed the curie test before
            term = TERM_SERVER.get_fragment(term)

        query_url = self.url % term  # any preprocessing of the term BEFORE here

        print('summary query url:', query_url)
        json = self.get(query_url)
        datasources = json['result']['federationSummary']['results']
        lit_count = json['result']['literatureSummary']['resultCount']
        nifid_count = {d['nifId']:d['count'] for d in datasources}
        nifid_count[LITERATURE_ID] = lit_count
        query =  json['query']  # includes expansions etc

        #TODO we need to gather all the metadata about the expansion used

        return nifid_count


###
#   Sorting!
###

class sortstuff:
    """ Class to hold all sort methods. NOTE: sortDim 0 -> terms, 1 -> src
        The key function should accept a tuple (id_, name) as an argument."""
    def __init__(self):
        # build a list of valid sort types from methods to populate the menus automatically
        sorts = []
        sort_terms = []
        sort_srcs = []
        same = []
        other = []
        for name in dir(self):
            if not name.startswith('_') and name != 'get_sort' and name != 'sort' and name != 'double_sort':
                if hasattr(getattr(self, name), '__terms_only__'):
                   sort_terms.append(name)
                elif hasattr(getattr(self, name), '__srcs_only__'):
                   sort_srcs.append(name)
                else:
                    sorts.append(name)
                    sort_terms.append(name)
                    sort_srcs.append(name)

                if hasattr(getattr(self, name), '__sort_same__'):
                    same.append(name)

                if hasattr(getattr(self, name), '__sort_other__'):
                    other.append(name)

        self.sort_types = ['single', 'double']
        self.sorts = sorts
        self.sort_terms = sort_terms
        self.sort_srcs = sort_srcs
        self.same = same
        self.other = other

        #bind term server
        self.term_server = TERM_SERVER

        # first pass alpha to avoid unstable sort issues
        self.sorted = lambda collection, key: sorted(sorted(collection), key=key)
        self._make_docs()

    def _make_docs(self):
        self.docs = {}
        for func in self.sorts:
            doc = getattr(self, func).__doc__
            if doc is None:
                doc = 'DOCUMENT ME PLEASE!'
            doc = ' '.join(doc.strip().rstrip().split())  # ah, the dirty join(split)
            self.docs[func] = doc

    def _asc(self, asc):
        return 1 if asc else -1

    def _invert_map(self, heatmap_data):
        inverted = {}
        for outer_key, dict_ in heatmap_data.items():
            for inner_key, number in dict_.items():
                if inner_key not in inverted:
                    inverted[inner_key] = {}

                inverted[inner_key][outer_key] = number

        return inverted

    def sort(self, sort_name, heatmap_data, idSortKey, ascending, sortDim, id_name_dict):
        """ This method is the only thing that should be called from other code. """
        print(sort_name, idSortKey, ascending, sortDim)
        id_sort, id_key = self.get_sort(sort_name, heatmap_data, idSortKey, ascending, sortDim)
        print(id_sort)
        id_order, name_order = [c for c in zip(*id_sort([(id_, name)  # format expected for key functions
                                for id_, name in id_name_dict.items()], key=id_key))]
        return id_order, name_order

    def double_sort(self, sort_name1, sort_name2, heatmap_data, idSortKey1, idSortKey2, ascending, sortDim, id_name_dict):
        """ This one may also be called externally. Should implement a rank-diff sort. """
        print('WHAT IS GOING ON HERE')
        ido1, no1 = self.sort(sort_name1, heatmap_data, idSortKey1, ascending, sortDim, id_name_dict)
        ido2, no2 = self.sort(sort_name2, heatmap_data, idSortKey2, ascending, sortDim, id_name_dict)

        id_sort = self.sorted
        id_key = lambda x: ido1.index(x[0]) - ido2.index(x[0])

        id_order, name_order = [c for c in zip(*id_sort([(id_, name)  # format expected for key functions
                                for id_, name in id_name_dict.items()], key=id_key))]

        return id_order, name_order
        id_sort1, id_key1 = self.get_sort(sort_name1, heatmap_data, idSortKey1, ascending, sortDim)
        id_sort2, id_key2 = self.get_sort(sort_name2, heatmap_data, idSortKey2, ascending, sortDim)

        new_key = lambda x: id_key1(x) - id_key2(x)  # FIXME this only works when all sort methods reduce to a numerical rank
        id_name_order = self.sorted([(id_, name) for id_, name in id_name_dict.items()], key=new_key)
        id_order, name_order = [c for c in zip(*out)]
        return id_order, name_order

    def get_sort(self, sort_name, heatmap_data, idSortKey, ascending, sortDim):
        return getattr(self, str(sort_name), self._default)(heatmap_data, idSortKey, ascending, sortDim)

    def _default(self, heatmap_data, idSortKey, ascending=True, sortDim=0):
        return self.alpha_id(heatmap_data, idSortKey, sortDim)

    def alpha_id(self, heatmap_data, idSortKey, ascending=True, sortDim=0):
        """ Sort alphabetically by identifier."""
        if not ascending:
            sorted_ = lambda c, key: sorted(c, key=key)[::-1]
        else:
            sorted_ = sorted

        key = lambda x: x[0]
        return sorted_, key

    def alpha_name(self, heatmap_data, idSortKey, ascending=True, sortDim=0):
        """ Sort alphabetically by name."""
        if not ascending:
            sorted_ = lambda c, key: sorted(c, key=key)[::-1]
        else:
            sorted_ = sorted

        key = lambda x: x[1]
        return sorted_, key

    @idSortOther
    def identifier(self, heatmap_data, idSortKey, ascending=True, sortDim=0):  # TODO
        """ Sort the values on an axis based by their relative rankings in
            the index identified by idSortKey (where key is Term or Source)
            on the other axis."""
        # identifier from opposite axis
        ascending = self._asc(ascending)
        if sortDim:  # normalize by total records for a given source
            key = lambda x: ascending * heatmap_data[idSortKey].get(x[0], 0) / heatmap_data[TOTAL_TERM_ID][x[0]]
        else:  # normalize by total hits for a given term
            def key(x):
                denom = sum(heatmap_data[x[0]].values())
                if not denom: # avoid division by zero
                    return 0
                numer = ascending * heatmap_data[x[0]].get(idSortKey, 0) 
                return numer / denom
            #key = lambda x: ascending * heatmap_data[x[0]].get(idSortKey, 0) / sum(heatmap_data[x[0]].values())   # FIXME division by zero is possible here!

        return self.sorted, key

    def frequency(self, heatmap_data, idSortKey, ascending=True, sortDim=0):
        """ Sort based on the number indicies (columns when rows, rows when columns)
            with at least one occurence divided by the total number of indicies.
            This gives a simple measure of frequency of occurance across data sources
            for a single term. This can be interpreted as diversity of use of a term
            or diversity of coverage for a datasource."""
        ascending = self._asc(ascending)
        if sortDim:
            key = lambda x: ascending * len([v for v in heatmap_data.values() if x[0] in v])
        else:
            key = lambda x: ascending * len([v for v in heatmap_data[x[0]].values() if v > 0])
        return self.sorted, key

    def total_count(self, heatmap_data, idSortKey, ascending=True, sortDim=0):
        """ Sort based on the sum of the values
            for all indicies on the opposite axis."""
        ascending = self._asc(ascending)
        if sortDim:
            key = lambda x: ascending * sum([v[x[0]] for v in heatmap_data.values() if x[0] in v])
        else:
            key = lambda x: ascending * sum([v for v in heatmap_data[x[0]].values() if v > 0])
        return self.sorted, key

    def name_length(self, heatmap_data, idSortKey, ascending=True, sortDim=0):
        """ Sort based on the number of characters in the name
            of the term or source."""
        ascending = self._asc(ascending)
        key = lambda x: ascending * len(x[1])
        return self.sorted, key

    @idSortSame
    def jaccard(self, heatmap_data, idSortKey, ascending=True, sortDim=0):
        """ Sort the values on an axis based on the jaccard index from a given
            value on that index. NOTE: Term and Source idSort are switched."""
        if sortDim:
            heatmap_data = self._invert_map(heatmap_data)

        ascending = self._asc(ascending)
        def key(x):
            ref = heatmap_data[idSortKey]
            targ = heatmap_data[x[0]]
            ref = set(ref)
            targ = set(targ)
            return ascending * len(ref.intersection(targ))/len(ref.union(targ))

        return self.sorted, key

    @idSortSame
    def num_common_same_axis(self, heatmap_data, idSortKey, ascending=True, sortDim=0):
        """ Sort the values on an axis based on the number of indexes on the other
            axis having at least one hit that also have at least one hit for 
            some reference value. NOTE: Term and Source idSort are switched."""
        if sortDim:
            heatmap_data = self._invert_map(heatmap_data)

        ascending = self._asc(ascending)
        def key(x):
            ref = heatmap_data[idSortKey]
            targ = heatmap_data[x[0]]
            rank = 0
            for key in ref:
                if key in targ:
                    rank += 1
            return ascending * rank

        return self.sorted, key

    @idSortSame
    def norm_from_same_axis(self, heatmap_data, idSortKey, ascending=True, sortDim=0):
        """ Sort the values on an axis by the distance between them where each row/column
            is treated as an n-dimensional vector where n is the number of indexes on
            the other axis. NOTE: Term and Source idSort are switched."""
        if sortDim:
            heatmap_data = self._invert_map(heatmap_data)
        
        ascending = self._asc(ascending)
        def key(x):
            ref = heatmap_data[idSortKey]
            targ = heatmap_data[x[0]]
            diffs = {}
            for key, r in ref.items():
                if key in targ:
                    diffs[key] = (r - targ[key]) ** 2
                else:
                    diffs[key] = r ** 2  # target value is zero

            for key, t in targ.items():
                if key not in diffs:
                    diffs[key] = t ** 2  # reference value is zero


            return ascending * sum(diffs.values()) ** .5

        return self.sorted, key

    @termsOnly
    def number_synonyms(self, heatmap_data, idSortKey, ascending=True, sortDim=0):
        ascending = self._asc(ascending)
        
        term_syn_dict = {}
        for term in heatmap_data:
            putative_term, curie, label, syns = self.term_server.term_id_expansion(term)
            term_syn_dict[term] = ascending * len(syns)

        print(term_syn_dict)

        def key(x):
            return term_syn_dict[x[0]]

        return self.sorted, key

    @termsOnly
    def number_edges(self, heatmap_data, idSortKey, ascending=True, sortDim=0):
        ascending = self._asc(ascending)
        term_edge_dict = {}
        for term in heatmap_data:
            putative_term, curie, label, syns = self.term_server.term_id_expansion(term)
            if curie:
                curie = curie.replace('#', '%23')  # FIXME FIXME this needs to be implemented in the scigraph client directly and/or fixed in the ontology or scigraph
                result = graph.getNeighbors(curie, depth=1, direction='BOTH')
                edges = result['edges']
                term_edge_dict[term] = ascending * len(edges)
            else:
                term_edge_dict[term] = 0
            
        def key(x):
            return term_edge_dict[x[0]]
        
        return self.sorted, key

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
    host = "localhost"#"postgres-stage.neuinfo.org"
    port = 5432
    DEBUG = True
    hstore = False
    def __init__(self):
        self.conn = pg.connect(dbname=self.dbname, user=self.user, host=self.host, port=self.port)
        if self.hstore:
            pg.extras.register_hstore(self.conn, globally=True)  # beware databases lacking this!
    def __enter__(self):
        return self
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
    hstore = True
    TERM_MIN = 5
    supported_filetypes = None, 'csv', 'tsv', 'html', 'json', 'png'  # need for output
    mimetypes = {None:'text/plain',
                 'csv':'text/csv',
                 'tsv':'text/tsv',
                 'html':'text/html',
                 'json':'application/json',
                 'png':'image/png'}

    collTerms = None, 'collapse terms by character number' , 'collapse terms by hierarchy'
    collSources = None, 'collapse views to sources', 'collapse names to sources'
    levels = [_ for _ in range(15)]

    termSortMethods = ('sort_alpha_id', 'sort_alpha_term', 'sort_frequency', 'sort_total_count', 'sort_name_length', 'sort_number_synonyms', 'sort_number_edges')
    srcSortMethods = ('sort_alpha_id', 'sort_alpha_term', 'sort_frequency', 'sort_total_count', 'sort_name_length')

    def __init__(self, summary_server):
        from .visualization import applyCollapse, dict_to_matrix, sCollapseToSrcId, sCollapseToSrcName, make_png
        self.applyCollapse = applyCollapse
        self.dict_to_matrix = dict_to_matrix
        self.sCollapseToSrcId = sCollapseToSrcId
        self.sCOllapseToSrcName = sCollapseToSrcName
        self.make_png = make_png
        super().__init__()
        self.summary_server = summary_server
        self.term_server = TERM_SERVER
        self.term_count_dict = {TOTAL_TERM_ID:{}}  # makes init play nice
        self.term_names = {TOTAL_TERM_ID:TOTAL_TERM_ID_NAME}  #FIXME these dicts may need to be ordered so we don't use too much memory
        self.heatmap_term_order = {}  # temp store of the original order
        self.resources = None
        self.check_counts()
        self.output_map = {
            None:self.output_json,
            'csv':self.output_csv,
            'tsv':self.output_tsv,
            'html':self.output_html,
            'json':self.output_json,
            'png':self.output_png,
                     }

        self.ppe = ProcessPoolExecutor()
        self.tpe = ThreadPoolExecutor(2)  # psycopg says this is safe?

        # this seems a bad way to pass stuff out to the webapp?
        ss = sortstuff()
        self.sort_docs = ss.docs
        self.sort_types = ss.sort_types
        self.sort_terms = ss.sort_terms
        self.sort_srcs = ss.sort_srcs
        self.sort_same = ss.same
        self.sort_other = ss.other
        self.sort = ss.sort
        self.double_sort = ss.double_sort

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
        heatmap = dict_to_matrix(hm_data, term_id_order, src_id_order, TOTAL_TERM_ID)[0]

    @sanitize_input
    def get_prov_from_id(self, hm_id, iso=True):
        sql = """SELECT datetime, filename FROM heatmap_prov WHERE id=%s;"""
        args = (hm_id,)
        tuples = self.cursor_exec(sql, args)
        if tuples:
            timestamp, filename = tuples[0]
            if iso:
                timestamp = timestamp.isoformat()
            return timestamp, filename if filename != None else ''
        else:
            return None, None

    def get_term_counts(self, cleaned_terms, *args, retry=True):  #FIXME this fails if given an id!
        """ given a collection of terms returns a dict of dicts of their counts
            this is where we make calls to summary_server, we are currently handling
            term failures in here which seems to make sense for time efficiency
        """
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
                except ConnectionError:
                    failed_terms.append(term)
                    continue

            term_count_dict[term] = nifid_count

        if failed_terms: print("Failed terms: ", failed_terms)
        
        #try the failed terms again, if the issue was a long timeout it should be cached by now
        if failed_terms and retry:
            fail_term_count_dict, failed_terms = self.get_term_counts(failed_terms, retry=False)
            term_count_dict.update(fail_term_count_dict)
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
    def submit_heatmap_job(self, cleaned_terms, filename=None):
        sql = "INSERT INTO job_to_heatmap_prov DEFAULT VALUES RETURNING id"
        [(job_id,)] = self.cursor_exec(sql)
        self.conn.commit()
        # FIXME this works for now... because mhd is mostly io bound so threads are ok
        #self.make_heatmap_data(cleaned_terms, job_id, filename)
        self.tpe.submit(self.make_heatmap_data, cleaned_terms, job_id, filename)  # XXX watch for silent faiures here!
        return job_id

    @sanitize_input
    def get_job(self, job_id):
        sql = "SELECT heatmap_prov_id FROM job_to_heatmap_prov WHERE id = %s"
        args = (job_id,)
        tuples = self.cursor_exec(sql, args)
        if not tuples:
            raise KeyError('No job with id = %s! Something has gone wrong!' % job_id)  # FIXME we don't want this :/
        else:
            [(hp_id,)] = tuples

        return hp_id

    @sanitize_input
    def make_heatmap_data(self, cleaned_terms, job_id, filename=None):  # FIXME error handling
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
        terms = cleaned_terms  # translation
        self.check_counts() #call to * to validate counts
        hm_data, fails = self.get_term_counts(terms)  # call this internally to avoid race conds
        
        terms = tuple(hm_data)  # prevent stupidity with missing TOTAL_TERM_ID

        if len(terms) <= self.TERM_MIN:  #TODO need to pass error back out for the web
            message = "We do not mint DOIS for heatmaps with less than %s terms."%self.TERM_MIN
            print(message)
            return hm_data, None, message

        if job_id is None:
            raise BaseException('We should NEVER ge here, self.TERM_MIN should always catch this.')

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
            args = (tuple(th_ids),)
            existing_hm_ids = self.cursor_exec(sql_hp_ids, args)

            sql = ("SELECT term_history_id FROM"
            " heatmap_prov_to_term_history WHERE heatmap_prov_id = %s")
            # we need hit the newest hm_ids first
            for (existing_hm_id,) in sorted(existing_hm_ids)[::-1]:
                print(existing_hm_id)
                args = (existing_hm_id,)
                all_old_th_ids = self.cursor_exec(sql, args)
                # unpack the tuple so it will match
                all_old_th_ids = [t[0] for t in all_old_th_ids]
                if set(th_ids) == set(all_old_th_ids):
                    sql_get_dt = "SELECT DateTime FROM heatmap_prov WHERE id=%s" 
                    args = (existing_hm_id,)
                    timestamp = self.cursor_exec(sql_get_dt, args)
                    sql_update_job = "UPDATE job_to_heatmap_prov SET heatmap_prov_id = %s WHERE id = %s"
                    job_args = (existing_hm_id, job_id)
                    self.cursor_exec(sql_update_job, job_args)
                    return hm_data, existing_hm_id, timestamp

        #create a new record in heatmap_prov since we didn't find an existing record
            #reccomend that users request the terms they need a single time for download
            #OR we just rate limit the number of heatmaps that can be requested XXX <-this
            #create the record
        sql_hp = "INSERT INTO heatmap_prov (filename) VALUES (%s) RETURNING id, DateTime"
        args = (filename,)
        [(hp_id, timestamp)] = self.cursor_exec(sql_hp, args)
        #hp_id = hp_result[0][0]

        #insert into heatmap_prov_to_term_history
            #XXX prov id #XXX history id pairs
        sql_add_junc = b"INSERT INTO heatmap_prov_to_term_history VALUES "#(%s,%s)"
        hp_ids = [hp_id] * len(th_ids)
        junc_args = (hp_ids, th_ids)
        sql_values = b",".join(self.mogrify("(%s,%s)", tup) for tup in zip(*junc_args))
        self.cursor_exec(sql_add_junc + sql_values)

        #update the job with the completed heatmap id, I feel like this *could* be done with a trigger, but would require dupe of job_id
        sql_update_job = "UPDATE job_to_heatmap_prov SET heatmap_prov_id = %s WHERE id = %s"
        job_args = (hp_id, job_id)
        self.cursor_exec(sql_update_job, job_args)

        #commit it (probably wrap this in a try/except)
        self.conn.commit()
        
        #store the original order of the terms in memory for now, maybe allow reup later w/ specific orders from elsewhere
        self.heatmap_term_order[hp_id] = terms

        return hm_data, hp_id, timestamp

    def output_csv(self, heatmap_data, term_name_order, src_name_order, term_id_order,
                   src_id_order, *args, sep=",", export_ids=True, **kwargs):
        """ consturct a csv file on the fly for download response """
        #this needs access id->name mappings
        #pretty sure I already have this written?
        matrix = dict_to_matrix(heatmap_data, term_id_order, src_id_order, TOTAL_TERM_ID)[0]
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

    def output_tsv(self, heatmap_data, term_name_order, src_name_order, term_id_order,
                   src_id_order, *args, sep=",", export_ids=True, **kwargs):
        """ tsv file output for jheatmaps """
        # TODO include the metrics rows/cols (frequecy, jarccard, etc) in the TSV for more sorting options
        max_count_len = 0  # because someone doesn't know how to write a natural sort
        for term in term_id_order:
            count = str(max([v for v in heatmap_data[term].values()]))
            if len(count) > max_count_len:
                max_count_len = len(count)
        single_pad = '0' * (max_count_len - 1)

        term_names = ['"%s"' % n if sep in n else n for n in term_name_order]
        src_names = ['"%s"' % n if sep in n else n for n in src_name_order]
        term_id_order = ['"%s"' % n if sep in n else n for n in term_id_order]  # deal with commas in names
        src_id_order = ['"%s"' % n if sep in n else n for n in src_id_order]  # probably dont need this here

        tab = '\t'
        header = '\t'.join(('source', 'term', 'count', 'link'))
        lines = header
        totals = heatmap_data['federation_totals']
        for term_name, term_id in zip(term_names, term_id_order):
            inner = heatmap_data[term_id.strip('"')]
            for src_name, src_id in zip(src_names, src_id_order):
                if src_id in inner:
                    total = totals[src_id] if totals[src_id] else 1
                    real_count = str(inner[src_id])
                    real_count = '0' * (max_count_len - len(real_count)) + real_count
                    #count = '{:3.4f}'.format((inner[src_id] / total) * len(totals))  # normalize by datasource size
                    count = real_count
                    count = '0' * (max_count_len - len(count)) + count
                else:
                    real_count = count = single_pad + '-'  # null works nicely here
                if src_id == 'nlx_82958':
                    if count == '0' * max_count_len:
                        count = single_pad + '-'  # literature is missed in check above
                    link = '<a href="http://neuinfo.org/literature/search?q='+term_id+'">'+real_count+'</a>'
                else:
                    link = '<a href="http://neuinfo.org/data/source/'+src_id+'/search?q='+term_id+'">'+real_count+'</a>'
                proto_line = '\t'.join((src_name, term_name, count, link))
                lines += '\n' + proto_line

        return lines, 'text/plain'

    def output_html(self, heatmap_data, term_name_order, src_name_order, term_id_order,
                   src_id_order, *args, sep=",", export_ids=True, **kwargs):
        term_name_order = list(term_name_order)
        term_id_order = list(term_id_order)
        
        html_string = '<table border=1 style="width:100%">'
        html_string += '<th><td>' + '</td><td>'.join(src_name_order) + '</td></th>'
        for term_id in term_id_order:
            term_name = term_id
            if term_id == 'federation_totals':
                term_name = '*'
            html_string += '<tr>'
            html_string += '<td>' + term_name + '</td>'
            for src_id in src_id_order:
                count = heatmap_data[term_id][src_id] if src_id in heatmap_data[term_id] else 0
                count = str(count)
                html_string += '<td>'
                datlit = 'data'
                if src_id == 'nlx_82958':
                    html_string += '<a href="http://neuinfo.org/literature/search?q='+term_id+'">'+count+'</a>'
                else:
                    html_string += '<a href="http://neuinfo.org/data/source/'+src_id+'/search?q='+term_id+'">'+count+'</a>'
                html_string += '</td>'
            html_string += '</tr>'
        html_string += '</table>'
    
        return html_string, self.mimetypes['html']

    def output_json(self, heatmap_data, *args, **kwargs):
        """ return a json object with the raw data and the src_id and term_id mappings """
        return json.dumps(heatmap_data), self.mimetypes['json']

    def output_png(self, heatmap_data, term_name_order, src_name_order, term_id_order, src_id_order, *args, title='heatmap', **kwargs):
        matrix, row_term_relation = dict_to_matrix(heatmap_data, term_id_order, src_id_order, TOTAL_TERM_ID)
        limit = 1000
        if len(matrix) > limit:
            #return "There are too many terms to render as a png. Limit is %s." % limit, self.mimetypes[None]
            matrix = matrix[:limit]
            term_name_order = term_name_order[:limit]
            src_name_order = src_name_order[:limit]
            term_id_order = term_id_order[:limit]
            src_id_order = src_id_order[:limit]

        if title.endswith('.png'):
            title = title[:-4]

        row_names = []
        for i in range(len(matrix)):
            row_names.append(row_term_relation[i])

        """
        row_names2 = []
        for item in term_name_order:
            if item not in row_names2:
                row_names2.append(item)
        row_names = []
        while len(row_names2) != 0:
            row_names.append(row_names2.pop(row_names2.index(min(row_names2))))
        """
        
        #row_names = term_name_order
        col_names = src_name_order
        destdir = '/tmp/'
        future = self.ppe.submit(self.make_png, matrix, row_names, col_names, title, destdir, poster=False, async=True)
        future.result()
        with open(destdir + '%s.png'%title, 'rb') as f:
            png = f.read()
        #png = self.make_png(matrix, row_names, col_names, title)
        return png, self.mimetypes['png']

    def input_validation(self, heatmap_data, *args, **kwargs):
        return None

    def explore(self, hm_id):  # TODO: match naming schemes so that the data organization lives here and the formatting lives in webapp?
        """ Generate the input data for select fields
            in a way that enables safe validation."""

        timestamp, filename = self.get_prov_from_id(hm_id)
        if not timestamp:
            return None, None  # FIXME make sure to map back to abort(404)
        else:
            date, time = timestamp.split('T')

        heatmap_data = self.get_heatmap_data_from_id(hm_id)


        tuples = [[v if v is not None else '' for v in self.term_server.term_id_expansion(term)]  # FIXME this called 2x
                  for term in heatmap_data]
        cuires = [t[1] for t in tuples if t[1]]
        relationship_types = tuple(set())  # TODO
        for tup in tuples:
            tup[-1] = str(tup[-1])  # convert syns -> query

        num_matches = len([t for t in tuples if t[1]])
        cols = [c for c in zip(*tuples)]
        justs = [max([len(s) for s in col]) + 1 for col in cols]
        cols2 = []
        for i, just in enumerate(justs):
            cols2.append([s.ljust(just) for s in cols[i]])

        titles = ''.join([s.ljust(just) for s, just
                          in zip(('Input', 'CURIE', 'Label', 'Query'), justs)])

        rows = [titles] + sorted([''.join(r) for r in zip(*cols2)])
        expansion = '\n'.join(rows)
        print("Expansion: ")
        print(expansion)

        explore_fields = {
            'hm_id':hm_id,
            'filename':filename,
            'num_terms':len(heatmap_data),
            'num_matches':num_matches,
            'time':time,
            'date':date,
            'expansion':expansion,
            'hier':'nameforhier0',
            'anysort':'name1', # FIXME better naming here?
            'ist':'name2',
            'irt':'name3',
            'iss':'name4',
            'irs':'name5',
            'secondSort':'sswoo',
            'anysort2':'name6', # FIXME better naming here?
            'ist2':'name7',
            'irt2':'name8',
            'iss2':'name9',
            'irs2':'name10',
            'idSortOps':str(self.sort_other).replace("'",'"'),
            'idRefOps':str(self.sort_same).replace("'",'"'),
        }
        print("IdSortOps")
        print(explore_fields['idSortOps'])

        srcs = sorted([(k, ' '.join(v)) for k, v in self.resources.items()], key=lambda a: a[1].lower())
        src_ids, src_names = [a for a in zip(*srcs)]

        select_mapping = {  # store this until... when?
                        'collTerms':(self.collTerms, ),
                        'collSources':(self.collSources, ),
                        'edges':(relationship_types, ),
                        'levels':(self.levels, ),
                        'sortTypeTerms':(self.sort_types, ),
                        'sortTypeSrcs':(self.sort_types, ),
                        'sortTerms':(self.sort_terms, ),
                        'sortSources':(self.sort_srcs, ),
                        'sortTerms2':(self.sort_terms, ),
                        'sortSources2':(self.sort_srcs, ),
                        'idSortTerms':(src_ids, src_names),
                        'idSortSources':(sorted(heatmap_data, key=lambda x: x.lower()), ),
                        'idRefTerms':(sorted(heatmap_data, key=lambda x: x.lower()), ),
                        'idRefSources':(src_ids, src_names),
                        'idSortTerms2':(src_ids, src_names),
                        'idSortSources2':(sorted(heatmap_data, key=lambda x: x.lower()), ),
                        'idRefTerms2':(sorted(heatmap_data, key=lambda x: x.lower()), ),
                        'idRefSources2':(src_ids, src_names),
                        'ascTerms':((True, False), ),
                        'ascSources':((True, False), ),
                        'filetypes':(sorted([str(m) for m in self.mimetypes]), ),
        }

        return explore_fields, select_mapping


    def output(self, heatmap_id, filetype, sortTerms=None, sortSources=None,  # FIXME probably want to convert the Nones for sorts to lists?
               collTerms=None, collSources=None, levels=0, idSortTerms=None, idSortSources=None,
               ascTerms=True, ascSources=True): 
        """
            Provide a single API for all output types.
        """
        if filetype not in self.output_map:
            return None, "Unsupported filetype!", None
        else:
            output_function = self.output_map[filetype]

        heatmap_data = self.get_heatmap_data_from_id(heatmap_id)
        if not heatmap_data:
            return None, "No heatmap with that ID!", None

        timestamp, _ = self.get_prov_from_id(heatmap_id)  # FIXME start/done timestamp? no answer to the yet :/
        timestamp = timestamp.replace(':','_')  # for consistency wrt attachment;
        filename = 'nif_heatmap_%s_%s.%s' % (heatmap_id, timestamp, filetype)

        # collapse rules and execution (need to go in their own function)
        # terms
        if collTerms == 'cheese':
            term_coll_function = lambda heatmap_data, term_id_name_dict: heatmap_data, term_id_name_dict
            term_id_name_dict = {id_:self.get_name_from_id(id_) for id_ in heatmap_data}
        elif collTerms == 'collapse terms by character number':
            term_coll_function = sCollToLength
            term_id_name_dict = {id_:self.get_name_from_id(id_) for id_ in heatmap_data}
        elif collTerms == 'collapse terms by hierarchy':
            term_coll_function = sCollByTermParent
            term_id_name_dict = {id_:self.get_name_from_id(id_) for id_ in heatmap_data}
        else:
            term_coll_function = None
            term_id_name_dict = {id_:self.get_name_from_id(id_) for id_ in heatmap_data}
        
        heatmap_data_copy = dict(heatmap_data)
        if filetype == "png":
            heatmap_data_copy.pop(TOTAL_TERM_ID)
            term_id_name_dict.pop(TOTAL_TERM_ID)
        
        if term_coll_function:
            if term_coll_function == sCollByTermParent:
                treeOutput = self.enrichment(term_id_name_dict)
                term_id_coll_dict, term_id_name_dict = term_coll_function(heatmap_data_copy, term_id_name_dict, treeOutput, int(levels))
            else: 
                term_id_coll_dict, term_id_name_dict = term_coll_function(heatmap_data_copy, term_id_name_dict)
            if idSortSources != None:
                for idSortSource in idSortSources:
                    if idSortSource not in term_id_coll_dict:  # note that idSortSources should be a TERM identifier
                        idSortSource = idSortSource.rsplit('-',1)[0]
                        if idSortSource not in term_id_coll_dict:
                            embed()
                            raise NameError('Identifier %s unknown!' % idSortSource)
        else:
            term_id_coll_dict = None

        # sources
        if collSources == 'cheese':
            src_coll_function = lambda heatmap_data_ttid, src_id_name_dict: heatmap_data_ttid, src_id_name_dict
            src_id_name_dict = {id_:self.get_name_from_id(id_) for id_ in heatmap_data[TOTAL_TERM_ID]}
        elif collSources == 'collapse views to sources':
            src_coll_function = self.sCollapseToSrcId
            src_id_name_dict = {id_:name_tup[0] for id_, name_tup in self.resources.items()}
        elif collSources == 'collapse names to sources':
            src_coll_function = self.sCollapseToSrcName
            src_id_name_dict = {id_:name_tup[0] for id_, name_tup in self.resources.items()}
        else:
            src_coll_function = None
            src_id_name_dict = {id_:' '.join(self.get_name_from_id(id_)) for id_ in heatmap_data[TOTAL_TERM_ID]}

        if src_coll_function:
            src_id_coll_dict, src_id_name_dict = src_coll_function(heatmap_data[TOTAL_TERM_ID], src_id_name_dict)
        else:
            src_id_coll_dict = None

        heatmap_data = dict(heatmap_data_copy)
        # apply the collapse dicts to the data, need to do before sorting for some sort options
        if term_id_coll_dict:
            heatmap_data = self.applyCollapse(heatmap_data, term_id_coll_dict, term_axis=True)

        if src_id_coll_dict:
            heatmap_data = self.applyCollapse(heatmap_data, src_id_coll_dict)

        #FIXME PROBLEMS KIDS
        #idSortTerms, idSortSources = idSortSources, idSortTerms

        # sort!
        term_id_order, term_name_order = self.sort(sortTerms,
                    heatmap_data, idSortTerms, ascTerms, 0, term_id_name_dict)
        src_id_order, src_name_order = self.sort(sortSources,
                    heatmap_data, idSortSources, ascSources, 1, src_id_name_dict)

        # TODO testing the double_sort, it works, need to update the output api to accomodate it
        #term_id_order, term_name_order = self.double_sort('identifier', 'frequency', heatmap_data, None, 'nlx_82958', ascTerms, 0, term_id_name_dict)

        if (filetype == "png" or filetype == "tsv"):
            termDict, srcDict = self.sortDict(heatmap_data)
            heatmap_data, term_id_order, src_id_order, term_name_order, src_name_order  = self.addSortToData(heatmap_data, term_id_order, src_id_order, term_name_order, src_name_order, termDict, srcDict)
        
        representation, mimetype = output_function(heatmap_data, term_name_order, src_name_order, term_id_order, src_id_order, title=filename)

        return representation, filename, mimetype

    def sortDict(self, heatmap_data):
        """
        Creates a dictionary that shows how terms should be sorted based on sort method. 
        Input: heatmap_data (the same heatmap_data that goes into the function "output"). It's a dictionary with a dictionary as values. 
        Output: two dictionaries. termOutput would look something like this:
            {sort_method0: {term_id0: 0, term_id1: 2, term_id2: 1}, 
            sort_method1: {term_id0: 5, term_id1: 2, term_id2: 13}, 
            sort_method2: term_id0: 2, term_id1: 1, term_id2: 0}}
            with the numbers representing either each term's rough position when sorted through or a calculated value unique to the sort method. The positions are zero-indexed. 
            sourceOutput follows the same format, but with sources instead of terms
        """
        termOutput = defaultdict(dict)
        sourceOutput = defaultdict(dict)
        term_id_name_dict = {id_:self.get_name_from_id(id_) for id_ in heatmap_data}
        src_id_name_dict = {id_:name_tup[0] for id_, name_tup in self.resources.items()}

        # All possible sort methods: alpha_id, alpha_term, frequency, identifier, total_count, name_length, jaccard, num_common_same_axis, norm_from_same_axis, number_synonyms, number_edges
        # Yet to be added: jaccard, identifier, num_common_same_axis, norm_from_same_axis

        # Sort: alpha_id. Sorting alphabetically by identifier
        term_identifier_dict = defaultdict(list)
        none_list = []
        
        for term in term_id_name_dict:
            if term == term_id_name_dict[term]:
                identifier = TERM_SERVER.term_id_expansion(term)[1]
            else:
                identifier = term
            if identifier == None:
                none_list.append(term)
            else:
                term_identifier_dict[identifier].append(term)

        term_identifier_list = sorted(term_identifier_dict, key=str.lower)    # Sort identifier_list by alphabetical order, regardless of upper/lowercase
        src_identifier_list = sorted(src_id_name_dict, key=str.lower)

        buffer = 0
        for term in none_list:
            termOutput["sort_alpha_id"][term] = buffer
            buffer += 1
        index = 0
        for identifier in term_identifier_list:
            for term in term_identifier_dict[identifier]:
                termOutput["sort_alpha_id"][term] = index + buffer
                index += 1
        for index, source in enumerate(src_identifier_list):
            sourceOutput["sort_alpha_id"][source] = index

        # Sort: alpha_term. Sorting alphabetically by term name
        term_dict = {}    # This is the exact opposite of term_id_name_dict; keys and values are swapped. This makes it convenient later when you have a term name, and need the identifier used in heatmap_data
        source_dict = {}

        for identifier in term_id_name_dict:
            term_dict[term_id_name_dict[identifier]] = identifier
        for source_id in src_id_name_dict:
            source_dict[src_id_name_dict[source_id]] = source_id

        term_list = sorted(term_dict, key=str.lower)
        source_list = sorted(source_dict, key=str.lower)

        for index, term in enumerate(term_list):
            termOutput["sort_alpha_term"][term_dict[term]] = index
        for index, source in enumerate(source_list):
            sourceOutput["sort_alpha_term"][source_dict[source]] = index

        # Sort: frequency. Sorting by how many sources a term appears in, divided by the total number of sources
        # Sort: total_count. Sort by the total number of times a term shows up across all sources
        term_frequency_count_list = []
        src_frequency_count_list = []
        for term in term_id_name_dict:
            frequency = len([v for v in heatmap_data[term].values() if v > 0])
            count = sum([v for v in heatmap_data[term].values() if v > 0])
            term_frequency_count_list.append((term, frequency, count))
        for source_id in src_id_name_dict:
            frequency = len([v for v in heatmap_data.values() if source_id in v])
            count = sum([v[source_id] for v in heatmap_data.values() if source_id in v])
            src_frequency_count_list.append((source_id, frequency, count))

        for tup in term_frequency_count_list:
            termOutput["sort_frequency"][tup[0]] = tup[1]
            termOutput["sort_total_count"][tup[0]] = tup[2]
        for tup in src_frequency_count_list:
            sourceOutput["sort_frequency"][tup[0]] = tup[1]
            sourceOutput["sort_total_count"][tup[0]] = tup[2]

        # Sort: name_length. Sort by length of term name, from smallest to greatest
        name_length_list = []
        src_length_list = []
        for term in term_list:
            name_length_list.append((term, len(term)))
        for source in source_list:
            src_length_list.append((source, len(source)))

        for tup in name_length_list:
            termOutput["sort_name_length"][term_dict[tup[0]]] = tup[1]
        for tup in src_length_list:
            sourceOutput["sort_name_length"][source_dict[tup[0]]] = tup[1]

        # Sort: number_synonyms. Sort by number of synonyms each term has
        # Sort: number_edges. Sort by number of edges each term has in the graph
        # These two sort methods are unique to terms only. Sources cannot be sorted this way
        term_edge_syn_list = []
        for term in term_id_name_dict:
            putative_term, curie, label, syns = self.term_server.term_id_expansion(term)
            if curie:
                curie = curie.replace('#', '%23')
                result = graph.getNeighbors(curie, depth=1, direction='BOTH')
                if result:
                    edges = result['edges']
                    term_edge_syn_list.append((term, len(edges), len(syns)))
                else: 
                    term_edge_syn_list.append((term, 0, len(syns)))
            else:
                term_edge_syn_list.append((term, 0, len(syns)))

        for tup in term_edge_syn_list:
            termOutput["sort_number_edges"][tup[0]] = tup[1]
            termOutput["sort_number_synonyms"][tup[0]] = tup[2]

        return termOutput, sourceOutput

    def addSortToData(self, heatmap_data, term_id_order, src_id_order, term_name_order, src_name_order, termDict, srcDict):
        """
        This function adds srcDict information to heatmap_data's outer dictionary, 
        and termDict information to heatmap_data's inner dictionary. 
        Also adjusts term_id_order and src_id_order
        Returns new heatmap_data, term_id_order, and src_id_order
        """
        for method in self.termSortMethods:
            for term in heatmap_data:
                heatmap_data[term][method] = termDict[method][term]
            src_id_order += method,
            src_name_order += method,

        for method in self.srcSortMethods:
            heatmap_data[method] = srcDict[method]
            term_id_order += method,
            term_name_order += method,
            
        return heatmap_data, term_id_order, src_id_order, term_name_order, src_name_order

    def enrichment(self, id_name_dict):
        """
        Takes in terms and outputs a tree with the common parent as the root
        Input: id_name_dict (dictionary, but anything that will iterate with the desired terms works)
        Output: tree, extra (the same type of stuff that comes from creatTree)
        """
        Query = namedtuple('Query', ['root','relationshipType','direction','depth'])

        relationship = 'subClassOf'
        direction = 'OUTGOING'
        
        try:
            id_name_dict.pop(TOTAL_TERM_ID)
        except KeyError:
            pass
    
        # Make trees for each term. Make a masterSet from the terms to find commonParent. Store nodes and edges
        listOfSetOfNodes = []
        listOfNodes = []
        listOfObjToSub = []
        listOfIdentifiers = []
        for term in id_name_dict:
            if term == id_name_dict[term]:
                identifier = TERM_SERVER.term_id_expansion(term)[1]
            else:
                identifier = term
            queryForTerm = Query(identifier, relationship, direction, 9)
            try:
                tree, extra = creatTree(*queryForTerm, graph=graph)
                nodes = extra[2]
                setOfNodes = set(nodes)
                listOfSetOfNodes.append(setOfNodes)
                listOfNodes.append(nodes)
                listOfObjToSub.append(extra[5])
                listOfIdentifiers.append(identifier)
            except:
                pass

        id_name_dict_expanded = {}    # Keep track of all identifiers and their true names
        for dicto in listOfNodes:
            for iden in dicto:
                id_name_dict_expanded[iden] = dicto[iden]
            
        # Make masterSet, which has all the nodes the terms share in common in their trees
        masterSet = listOfSetOfNodes[0]
        for setOfNodes in listOfSetOfNodes:
            masterSet = masterSet & setOfNodes

        masterSet.remove('CYCLE DETECTED DERPS')
        searchCP = set()    # searchCP will be used to find the commonParent. 
        for item in masterSet:
            searchCP.add(item)
        
        # Keeping track of all the edges via objects and subjects (object --> subject)
        edges0 = []
        edges1 = []
        for pair in listOfObjToSub:
            for obj in pair.keys():
                sub = pair[obj]
                for item in sub:
                    edges0.append(obj)
                    edges1.append(item)
        
        # Prunning the tree. Only the search terms should be at the bottom of the tree anyway; the rest is extra that we don't need
        fullPrun = False
        while not fullPrun:
            fullPrun = True
            toRemove = []
            for sub in edges1:
                if sub not in edges0 and sub not in listOfIdentifiers:
                    toRemove.append(sub)
                    fullPrun = False
            for sub in toRemove:
                index = edges1.index(sub)
                edges0.pop(index)
                edges1.pop(index)
        
        # tempEdgeDict will help us in our search for the commonParent. It contains the information of edges0 and edges1 in dictionary format, making it easy to access
        tempEdgeDict = defaultdict(set)
        for i in range(len(edges0)):
            tempEdgeDict[edges0[i]].add(edges1[i])

        def recDict():
            return defaultdict(recDict)
        def fillTree(node, tree):
            if node not in tempEdgeDict.keys():
                return
            for sub in tempEdgeDict[node]:
                tree[node][sub]
                fillTree(sub, tree[node])


        # Find the commonParent. If searchCP is empty for some reason, the commonParent is owl#Thing by default
        try:
            searchCont = True
            commonParent = searchCP.pop()
            while searchCont:
                matchFound = True
                tempTree = recDict()
                fillTree(commonParent, tempTree)
                for item in searchCP:
                    if in_tree(item, tempTree):
                        itemInTree = True
                        if itemInTree:
                            commonParent = item
                            searchCP.remove(item)
                            matchFound = False
                            break
                if not matchFound:
                    searchCont = False
            masterSet.remove(commonParent)
        except KeyError:
            commonParent = "http://www.w3.org/2002/07/owl#Thing"
            
        # Find rank (actually called "degree")  for each node. This dict also eliminates any nodes not directly related to commonParent (must be children)
        rankDict = {}
        def fillRankDict(identifier):
            rankDict[identifier] = 0
            for node in tempEdgeDict[identifier]:
                fillRankDict(node)
                rankDict[identifier] += rankDict[node] + 1
        
        # edges0 and edges1 have duplicate entries. To eliminate this problem, we'll use our old friend tempEdgeDict! And we'll also fill our rankDict
        edges0 = []
        edges1 = []
        for obj in tempEdgeDict.keys():
            for sub in tempEdgeDict[obj]:
                edges0.append(obj)
                edges1.append(sub)
        fillRankDict(commonParent)

        # Take out edges not included in rankDict
        toRemove = []
        for obj in edges0:
            if obj not in rankDict.keys():
                toRemove.append(obj)
        for obj in toRemove:
            index = edges0.index(obj)
            edges0.pop(index)
            edges1.pop(index)
        toRemove = []
        for obj in edges1:
            if obj not in rankDict.keys():
                toRemove.append(obj)
        for obj in toRemove:
            index = edges1.index(obj)
            edges0.pop(index)
            edges1.pop(index)
            
        # If there are two branches going upward from a node, we need to take care of that!
        toRemove = []
        for sub in edges1:
            if edges1.count(sub) > 1 and sub not in toRemove and sub in rankDict.keys():
                toRemove.append(sub)
        toRemove = sorted(toRemove, key=lambda x: rankDict[x])
        toRemove.reverse()
        
        def eraseUpwardEdges(sub):
            """
            Erase extra edges in the case of multiple branches from a single node going toward commonParent's direction
            """
            def travelUp(sub, index):
                """
                Return a set of parents for a certain branch upward
                """
                obj = edges0[index]
                return travelUpHelper(obj)
            def travelUpHelper(sub):
                result = set()
                result.add(sub)
                if sub == commonParent or sub not in rankDict.keys():
                    return result
                for i, subj in enumerate(edges1):
                    if subj == sub:
                        obj = edges0[i]
                        moreParents = travelUpHelper(obj)
                        for item in moreParents:
                            result.add(item)
                return result           
                
            indexOfSet = 0
            travelPath = []
            for i, subj in enumerate(edges1):
                if subj == sub:
                    setOfParents = travelUp(sub, i)
                    travelPath.append(setOfParents)
              
            # Find the common node that all the branches share      
            masterParentSet = travelPath[0]
            for parentSet in travelPath:
                masterParentSet = masterParentSet & parentSet
            try:
                miniCommonParent = masterParentSet.pop()
            except:
                embed()
            foundCommonParent = False
            while not foundCommonParent:
                miniCommonChildren = tempEdgeDict[miniCommonParent]
                for item in miniCommonChildren:
                    done = True
                    if item in masterParentSet:
                        miniCommonParent = item
                        done = False
                if done:
                    foundCommonParent = True
            
            # Look at the children of the common node. The one with the highest rank is part of the branch we want to keep. The other ones will be taken out
            miniChildren = tempEdgeDict[miniCommonParent]
            miniChildrenRank = []
            for child in miniChildren:
                for path in travelPath:    # This ensures the child exists in one of the paths to sub
                    if child in path:
                        miniChildrenRank.append(child)
                        break
            miniChildrenRank = sorted(miniChildrenRank, key=lambda x: rankDict[x])
            miniChildrenRank.pop()    # The child with the largest rank was popped. The ones that need to be removed remain. 

            # Taking out the unnecessary branches
            for child in miniChildrenRank:
                for path in travelPath:
                    if child in path:
                        parentalNode = path.pop()
                        trueParent = False
                        while trueParent:
                            children = tempEdgeDict[parentalNode]
                            foundParent = True
                            for item in children:
                                if item in path:
                                    parentalNode = item
                                    foundParent = False
                                    break
                            if foundParent:
                                trueParent = True
                for i, obj in enumerate(edges0):
                    try:
                        obj == parentalNode
                    except:
                        embed()
                    if obj == parentalNode and edges1[i] == sub:
                        edges0.pop(i)
                        edges1.pop(i)
        
        for sub in toRemove:
            eraseUpwardEdges(sub)
        
        # With excess edges removed, time to prune again!
        fullPrun = False
        while not fullPrun:
            fullPrun = True
            toRemove = []
            for sub in edges1:
                if sub not in edges0 and sub not in listOfIdentifiers:
                    toRemove.append(sub)
                    fullPrun = False
            for sub in toRemove:
                index = edges1.index(sub)
                edges0.pop(index)
                edges1.pop(index)
        
        # Create newEdgeDict. It includes the new changes from taking out excess branches
        newEdgeDict = defaultdict(set)
        for i in range(len(edges0)):
            newEdgeDict[edges0[i]].add(edges1[i])

        # Make the json file we need to feed into creatTree
        resultJson = defaultdict(list)    
        for obj in newEdgeDict.keys():
            for sub in newEdgeDict[obj]:
                miniDict = {}    # "sub" is "pred" of "obj"
                miniDict['meta'] = ""
                miniDict['sub'] = sub
                miniDict['obj'] = obj
                miniDict['pred'] = relationship
                resultJson['edges'].append(miniDict)
        setOfObj = set(edges0)
        setOfSub = set(edges1)
        setOfAllNodes = setOfObj | setOfSub
        for identifier in setOfAllNodes:
            try:
                name = id_name_dict_expanded[identifier]
            except:
                name = ""
            miniDict = {'id': identifier, 'lbl': name}
            resultJson['nodes'].append(miniDict)
        resultJson = dict(resultJson)
        resultJson = json.dumps(resultJson)
        resultJson = json.loads(resultJson)
        
        invdir = {'INCOMING':'OUTGOING','OUTGOING':'INCOMING'}[direction]
        resultTree = creatTree(commonParent, relationship, invdir, 9, graph=graph, json=resultJson)
        
        return resultTree
    
        

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
    
    jss = json_summary_service()
    xss = summary_service()
    #test terms
    brain = 'UBERON_0000955'

    # make sure to from desc.prof import profile_me and decorate
    # run twice to make sure that the result is cached
    jss.get_sources()
    jss.get_counts(brain)

    xss.get_sources()
    xss.get_counts(brain)
    
    #embed()


if __name__ == '__main__':
    main()
