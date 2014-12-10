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

#xpaths
term_id_xpath = "//class[not(contains(id,'NEMO'))]/id/text()"
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

def get_rel_id(relationship):  #FIXME this is NOT consistently ordred! AND is_a and part_of behave VERY differently!
    """
        Used to get relationship ids so that xpath queries will actually work :/
    """
    query_url = url_oq_gp_term + relationship
    response = requests.get(query_url)
    ids = get_xpath(response.text, rel_id_xpath%relationship)
    #embed()
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

    rel_id = get_rel_id(relationship)  # we do this up here we don't look it up every time

    def inner(parent_id, level):
        """ because fuck relationship and being able to dynamically
            reconfigure on the way down the tree yay namespaces
        """

        response = requests.get(url_oq_rel%parent_id)  #FIXME brain returns a truncated result ;_; that is what is breaking things!

        if child_relationship == "subject":
            xpath = child_term_ids_subject_xpath%(parent_id, rel_id)
        else:
            xpath = child_term_ids_object_xpath%(parent_id, rel_id)

        id_list = get_xpath(response.text, xpath)  # FIXME not clear if this is returning what we want across all levels of the tree

        if level == 1:
            out = [id_.content for id_ in id_list]
            #print(out)
            #embed()
            return out
        else:
            ids = []
            new_level = level - 1
            for id_ in id_list:
                ids += inner(id_, new_level)
            return ids

    return inner(parent_id, level)




def main():


    #tl = ["brain", "cell", "protein", "hippocampus", "ion channel", "calcium"]
    tl = ["brain"]
    level = 1  #seems we need to stick with this for now because level = 2 => destroy the server
    #relationship = 'part_of'
    relationship = 'has_proper_part'  #FIXME the results of the query are truncated so we never get to these!
    child_relationship = 'subject'
    #child_relationship = None # use this for brain (mine is currently full of wat)


    #get_rel_id(relationship)
    #return

    out = [get_term_id(t) for t in tl]
    print(out)
    childs = {}
    for id_ in out:
        if id_ != None:
            childs[id_] = get_child_term_ids(id_, level, relationship, child_relationship)
    print(childs)


if __name__ == "__main__":
    main()
