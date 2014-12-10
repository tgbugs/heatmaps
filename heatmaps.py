#!/usr/bin/env python3.4
"""
Usage:
    heatmaps.py
"""
import requests
import libxml2
from IPython import embed
from docopt import docopt

args = docopt(__doc__, version='heatmaps .0001')


#urls
url_oq_con_term = "http://nif-services.neuinfo.org/ontoquest/concepts/term/"  #used in get_term_id
url_oq_gp_term = "http://nif-services.neuinfo.org/ontoquest/getprop/term/"  # used to get the id for relationship
url_oq_rel = "http://nif-services.neuinfo.org/ontoquest/rel/all/%s?level=1&includeDerived=true&limit=0"  # %s is id
url_serv_summary = "http://nif-services.neuinfo.org/servicesv1/v1/summary?q="

#xpaths
term_id_xpath = "//class[not(contains(id,'NEMO'))]/id/text()"  #FIXME ok for some reason the non-nemo id gives SHIT results
#term_id_xpath = "//class[contains(id,'NEMO')]/id/text()"  #FIXME NEVER MIND! that tree goes nowhere ;_;
rel_id_xpath =  "//class[not(contains(id,'%s'))]/id/text()"  # %s should be relationship here!
child_term_ids_object_xpath = "//relationship[object/@id='%s' and property/@id='%s']/subject/@id"  # %s id %s relationship
child_term_ids_subject_xpath = "//relationship[subject/@id='%s' and property/@id='%s']/object/@id"

class Summary:
    "the summary xml"


def get_xpath(doc, query):
    """ doc is a string that is an xml document
        query is a string that is a valid xpath query
        returns a list of nodes
    """
    node = libxml2.parseDoc(doc)
    xpc = node.xpathNewContext()
    return xpc.xpathEval(query)

def run_xpath(url, query):
    #xmlDoc = libxml2.parseEntity(url)  #XXX this causes hangs due to no timeout
    try:
        resp = requests.get(url, timeout=2)
    except requests.exceptions.Timeout:
        return [None]
    xmlDoc = libxml2.parseDoc(resp.text)
    xpc = xmlDoc.xpathNewContext()
    return xpc.xpathEval(query)

def get_rel_id(relationship):  #FIXME this is NOT consistently ordred! AND is_a and part_of behave VERY differently!
    """
        Used to get relationship ids so that xpath queries will actually work :/
    """
    query_url = url_oq_gp_term + relationship
    #response = requests.get(query_url)
    #ids = get_xpath(response.text, rel_id_xpath%relationship)

    ids = run_xpath(query_url, rel_id_xpath%relationship)
    print([t.content for t in ids])
    try:
        id_ = ids[0].content
    except IndexError:
        id_ = None
    return id_


def get_term_id(term):
    """ Return the id for a term or None if an error occures """
    query_url = url_oq_con_term + term.replace(" ", "%20")
    response = requests.get(query_url)
    ids = get_xpath(response.text, term_id_xpath)
    embed()
    #ids = run_xpath(query_url, term_id_xpath)
    try:
        id_ = ids[0].content
    except IndexError:
        id_ = None
    return id_

def get_child_term_ids(parent_id, level, relationship, child_relationship):
    """ This was burried deep within the tree of kepler actors making it nearly
        impossible to find the actual data. Also, who though that using the
        equivalent of environment variables to pass global information down
        a giant tree of actors was a remotely good idea?

        NOTE: the terms are unordered, not entierly clear when we should try
        to order them

        this will concat all the way up, flattening the tree at that level
        yay dev tools level fail
    """
    #TODO: allow more dynamic traversal of the tree by stoping at nodes where
    #the reference count is zero for all children so we can show relative depth
    #esp. important for coverage of species


    #response = requests.get(url_oq_rel%parent_id)  #FIXME brain returns a truncated result ;_; that is what is breaking things!

    if child_relationship == "subject":
        xpath = child_term_ids_subject_xpath%(parent_id, relationship)
    else:
        xpath = child_term_ids_object_xpath%(parent_id, relationship)



    #id_list = [n.content for n in get_xpath(response.text, xpath)]  # FIXME not clear if this is returning what we want across all levels of the tree
    query_url = url_oq_rel%parent_id

    id_list = [n.content for n in run_xpath(query_url, xpath)]


    if level == 1:
        #print(id_list)
        print('level',level,'parent_id',parent_id,'ids',id_list)
        xnames = "//relationship[subject/@id='%s' and property/@id='%s']/object"%(parent_id, relationship)
        print([n.content for n in run_xpath(query_url, xnames)])  #FIXME MMMM HIT DAT SERVER

        return id_list
    else:
        ids = []
        new_level = level - 1
        for id_ in id_list:
            ids += get_child_term_ids(id_, new_level, relationship, child_relationship)  #funstuff here with changing the rels
        print('level',level,'parent_id',parent_id,'ids',ids)
        return ids

def get_summary_counts(id_):
    print('getting summary for', id_)
    query_url = url_serv_summary + id_
    nodes = run_xpath(query_url, '//results/result')
    if nodes:
        if nodes[0] == None:
            return id_, ['An error was encounter while retrieving counts.']
    name = run_xpath(query_url, '//clauses/query')[0].content  # FIXME please don't hit this twice ;_;


    nifIds = []
    dbs = []
    indexables = []
    counts = []

    for node in nodes:
        if node.prop('nifId') not in nifIds:  #TODO should we have a simple way to generalize schemas of attributes + content > columns?
            nifId = node.prop('nifId')
            db =  node.prop('db')
            indexable = node.prop('indexable')
            cs = node.xpathEval('./count')
            if len(cs) > 1:
                print(id_, name, [c.content for c in cs])
                raise IndexError('too many counts!')
            count = cs[0].content

            nifIds.append(nifId)
            dbs.append(db)
            indexables.append(indexable)
            counts.append(count)
        else:
            print(node.prop('nifId'))

    print(dbs)
    return name, [a for a in zip(nifIds, dbs, indexables, counts)]



    #counts = get_xpath(response.text, term_id_xpath)


problem_ids = ['birnlex_1700', 'birnlex_1571', 'birnlex_1570','birnlex_1577',
               'birnlex_1576','birnlex_1575','birnlex_1574','birnlex_1170',
               'birnlex_1581','birnlex_1583','birnlex_1586',
              ]  # report these, some seem to be redirects in neurolex and a number w/ PONS_brain_region
                 # or regional part of the brain
                 # fairley certain that the stuff that succeeds is cached and that I broke the service

def main():
    #tl = ["brain", "cell", "protein", "hippocampus", "ion channel", "calcium"]
    #tl = ['midbrain']
    #relationship = 'part_of'
    #relationship='proper_part_of'

    #tl = ['Central nervous system']
    #relationship = 'has_proper_part'  #FIXME the results of the query are truncated so we never get to these!
    #child_relationship = 'subject'  # this works for 'Central nervous system' but not for brain :/


    #all my wat: there is no tree O_O why!?!?!?!?!
    tl = ["brain"]  #FIXME for reasons I do not entirely understand 
    relationship = get_rel_id('has_part')
    #relationship = 'has_proper_part'  # with the NEMO id :/ all my wat
    child_relationship = 'subject' # use this for brain (mine is currently full of wat) this seems backward from wf

    level = 1  #seems we need to stick with this for now because level = 2 => destroy the server

    #get_rel_id(relationship)
    #return

    term_ids = [get_term_id(t) for t in tl]
    print(term_ids)

    childs = {}
    datas = {}
    for term_id in term_ids:
        if term_id != None:
            child_ids = get_child_term_ids(term_id, level, relationship, child_relationship)
            childs[term_id] = child_ids
            child_data = {}
            continue
            for child_id in child_ids[0:100]:
                if child_id in problem_ids:
                    continue
                data = get_summary_counts(child_id)
                print(data)
                child_data[child_id] = data
            datas[term_id] = child_data  # so I heard you like dicts so I put dicts in ur dicts


    embed()

if __name__ == "__main__":
    main()
