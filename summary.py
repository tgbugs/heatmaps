#!/usr/bin/env python3
"""
    This file contains the code that:
    1) retrieves data from the summary service on a term by term basis
    2) maintains records for common terms (cache)
    3) manages the provenance for specific heatmaps that have been saved
    4) maintains collapse maps??? or should this happen independently?

"""

import psycopg2
import requests  #XXX switching to json because requests autodecodes to dict :D

from IPython import embed

#SHOULD PROV also be handled here?
#SHOULD odering of rows and columns go here?

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
#   Base urls that may change
###

SCIGRAPH = "http://matrix.neuinfo.org:9000"

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
    def __new__(cls):
        if cls._cache_xml:
            cls._xml_cache = {}
        return cls

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




    def xpath(self, xml, queries*):
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
            return result






###
#   Retrieve summary per term
###

# 1) DEDUPLICATE RECORDS WHY!? WHY!?

class summary_service(rest_service):  #implement as a service/coro? with asyncio?
    url = "http://nif-services.neuinfo.org/servicesv1/v1/summary.xml?q="

    def __init__(self, term_server):  # FIXME this feels wrong :/
        self.term_server = term_server
    
    def get_counts(self, term):
        term_id = self.term_server.get_id(term)





###
#   Map terms to ids  FIXME we need some way to resolve multiple mappings to ids ;_;
###
class term_service(rest_service):
    """ let us try this with json """
    url = SCIGRAPH + "/scigraph/vocabulary/term/%s.json?limit=20&searchSynonyms=true&searchAbbreviations=false&searchAcronyms=false"  #FIXME curie seems borken?

    def get_id(self, term):
        query_url = self.url % term
        records = self.get_json(query_url)['concepts']
        identifiers = [record['fragment'] for record in records if not record['deprecated']]
        return identifiers[0]  #FIXME this is a stupid way to resolve the problem of multiple ids


###
#   Stick the collected data in a datastore (postgres)
###



###
#   main
###

def main():
    rs = rest_service()
    embed()

if __name__ == '__main__':
    main()
