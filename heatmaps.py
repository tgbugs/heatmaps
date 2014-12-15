"""
Usage:
    heatmaps.py
"""
from IPython import embed  #FIXME name collisions sadness
import requests
import libxml2
import numpy as np
import pylab as plt
from docopt import docopt

args = docopt(__doc__, version='heatmaps .0001')


# NOTES: normalize by the first appearance of the term in the literature to attempt to control for historical entrenchment
# consider also normalizing by the total number of records per datasource??

#urls
url_oq_con_term = "http://nif-services.neuinfo.org/ontoquest/concepts/term/"  #used in get_term_id
url_oq_gp_term = "http://nif-services.neuinfo.org/ontoquest/getprop/term/"  # used to get the id for relationship
url_oq_rel = "http://nif-services.neuinfo.org/ontoquest/rel/all/%s?level=1&includeDerived=true&limit=0"  # %s is id
url_serv_summary = "http://nif-services.neuinfo.org/servicesv1/v1/summary.xml?q="

#xpaths
term_id_xpath = "//class[not(contains(id,'NEMO'))]/id/text()"  #FIXME ok for some reason the non-nemo id gives SHIT results
#term_id_xpath = "//class[contains(id,'NEMO')]/id/text()"  #FIXME NEVER MIND! that tree goes nowhere ;_;
rel_id_xpath =  "//class[not(contains(id,'%s'))]/id/text()"  # %s should be relationship here!
child_term_ids_object_xpath = "//relationship[object/@id='%s' and property/@id='%s']/subject/@id"  # %s id %s relationship
child_term_ids_subject_xpath = "//relationship[subject/@id='%s' and property/@id='%s']/object/@id"

#files
file_birnlex_796_rel = "~/Downloads/birnlex_796.xml"


def re_tree_der():
    """
        A rel/all dump with includeDerived=ture on brain flattens everything, the tree is still there, but we have to
        recreate it

        JUST KIDDING! not actually possible because they real did flatten it >_<
    """

    xmlDoc = libxml2.parseEntity(file_birnlex_796_rel)
    c = xmlDoc.xpathNewContext()
    child_term_ids_xpath = "//relationship[subject/@id='%s' and property/@id='%s']/subject/@id"%('birnlex_768',)  # %s id %s relationship
    c.xpathEval(child_term_ids_xpath)


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

def run_xpath(url, *queries):
    #xmlDoc = libxml2.parseEntity(url)  #XXX this causes hangs due to no timeout
    try:
        resp = requests.get(url, timeout=8)  # sometimes we need a longer timeout :/
    except requests.exceptions.Timeout:
        return [None]
    xmlDoc = libxml2.parseDoc(resp.text)
    xpc = xmlDoc.xpathNewContext()
    out = []
    for query in queries:
        out.append(xpc.xpathEval(query))
    if len(queries) == 1:
        return out[0]
    return out

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
    #embed()
    #ids = run_xpath(query_url, term_id_xpath)
    try:
        id_ = ids[0].content
    except IndexError:
        id_ = None
    return id_

def get_child_term_ids(parent_id, level, relationship, child_relationship, exclude_parents=False):
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
        xnames = "//relationship[subject/@id='%s' and property/@id='%s']/object"%(parent_id, relationship)
    else:
        xpath = child_term_ids_object_xpath%(parent_id, relationship)
        xnames = "//relationship[object/@id='%s' and property/@id='%s']/subject"%(parent_id, relationship)



    #id_list = [n.content for n in get_xpath(response.text, xpath)]  # FIXME not clear if this is returning what we want across all levels of the tree
    query_url = url_oq_rel%parent_id

    id_nodes, name_nodes = run_xpath(query_url, xpath, xnames)
    #id_list = [i.content for i in id_nodes]
    id_name_idct = {id_:n.content for id_, n in zip(id_nodes, name_nodes)}


    if level == 1:
        #print(id_list)
        print('level',level,'parent_id',parent_id,'ids',id_list)
        #print([n.content for n in run_xpath(query_url, xnames)])  #FIXME MMMM HIT DAT SERVER

        return id_name_dict
        #return id_list
    else:
        child_dicts = []
        new_level = level - 1
        for id_ in id_name_dict.keys():
            new_dict = get_child_term_ids(id_, new_level, relationship, child_relationship)  #funstuff here with changing the rels
            child_dicts.append(new_dict)
        if exclude_parents:
            id_name_dict = {}
        for dict_ in child_dicts:
            id_name_dict.update(dict_)
        print('level',level,'parent_id',parent_id,'ids',id_name_dict)
        return id_name_dict

def get_summary_counts(id_):
    print('getting summary for', id_)
    query_url = url_serv_summary + id_
    nodes = run_xpath(query_url, '//results/result')
    if nodes:
        if nodes[0] == None:
            return [('error-0',id_,'ERROR', -100)]
    name = run_xpath(query_url, '//clauses/query')[0].content  # FIXME please don't hit this twice ;_;
    print(name)


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
            count = int(cs[0].content)

            nifIds.append(nifId)
            dbs.append(db)
            indexables.append(indexable)
            counts.append(count)
        else:
            print(node.prop('nifId'))

    print(dbs)
    return [a for a in zip(nifIds, dbs, indexables, counts)]



    #counts = get_xpath(response.text, term_id_xpath)


def get_term_count_data(term, level, relationship, child_relationship):
    """
        for a given term go get all its children at a given level and get the
        counts for their instances across databases
    """
    term_id = get_term_id(term)
    child_data = {}
    if term_id != None:
        child_ids = get_child_term_ids(term_id, level, relationship, child_relationship)
        for child_id in child_ids:#[0:10]:
            data = get_summary_counts(child_id)
            print(data)
            child_data[child_id] = data
    return child_data

problem_ids = ['birnlex_1700', 'birnlex_1571', 'birnlex_1570','birnlex_1577',
               'birnlex_1576','birnlex_1575','birnlex_1574','birnlex_1170',
               'birnlex_1581','birnlex_1583','birnlex_1586',
              ]  # report these, some seem to be redirects in neurolex and a number w/ PONS_brain_region
                 # or regional part of the brain
                 # fairley certain that the stuff that succeeds is cached and that I broke the service


# converting terms and data sources (and eventually anything) into a reliably indexed matrix
# as long as we know the mapping from the ids to the reference table the order actually doesnt matter
# in fact it may make life easier if we can just add new sources on to the end (eh)
# the ids will be used to generate a REFERENCE matrix where ids are mapped to natural numbers 0-n
# various orderings of the ids will be mapped to permutations of the original index
# eg aijth term from the reference matrix will be placed in the bxyth position when a new ordering
# maps i->x and j->y
# aij i->rows j->columns as per convention, we will make the term ids the rows and the source (etc) ids the columns
# this works nicely with the fact that each row has only a subset of the sources
# WE NEED to have the FULL list of terms 
# consideration: the list of terms probably changes more quickly than the list of sources, another argument for keeping
# terms as rows since we will have to iterate over all terms when we index a new source anyway
# XXX DERP just keep the bloody thing in dict form and use the orderings from there
# all we need to know is how many total data sources there are and what index we want to use for each of them (ie we need to fill in the zeros)
# XXX may still want this becasue if we want to reorder on data sources it is going to be a pain if we can't use slicing

full_list_of_datasource_nifids = []  # this is useful if we don't know the number of terms and haven't made a matrix, just a set of lists
map_of_datasource_nifids = {} # better to use a dict to map id -> index  XXX validate uniqueness

def get_source_entity_nifids():
    #TODO  WHERE DO THESE ACTUALLY COME FROM!??!!?!
    query_url = url_serv_summary + "*"
    nodes = run_xpath(query_url, '//result/@nifId')  #todo, we may need to also get the name out here :/
    ids = []
    for n in nodes:
        if n.content not in ids:
            ids.append(n.content)
    print(ids)
    return ids

def construct_columns(data_dict, term_id_list, datasource_nifid_list):
    """
        Given two lists of ids, the first list will be rows the 2nd will be comluns
        The values first list should match the keys in the data dict

        The orderings of both indexes are stored in term_id_list and datasource_nifid_list
        and those can be used to reorder the matrix, or maybe we just call this function again.
    """
    n_cols = len(datasource_nifid_list)

    #make a lookup dict to map nifids to indexes for faster updates
    nid_map = {nid:i for i, nid in enumerate(datasource_nifid_list)}

    rows_to_vstack = []
    for term_id in term_id_list:
        data_list = data_dict[term_id]
        row = np.zeros((n_cols))
        for nifId, _, _, count in data_list:
            if count >= 0:  #ignore errors
                row[nid_map[nifId]] = count
        rows_to_vstack.append(row)

    data_matrix = np.vstack(rows_to_vstack)
    print(data_matrix)
    return data_matrix

def discretize(data_matrix):
    bins = [0,1,10,100]
    vals = [0,1,2,3]

    #for l in bins[:-1]:
        #for u in bins[1:]:
            #f_m = (data_matrix > l) * (data_matrix <= u)
            #data_matrix[f_m]

    for lower, upper, val in zip(bins[:-1],bins[1:], vals[:-1]):
        data_matrix[ (data_matrix >= lower) * (data_matrix < upper) ] = val

    data_matrix[data_matrix >= bins[-1]] = vals[-1]

    return data_matrix


def display_heatmap(matrix, row_names, col_names, title):
    #size = (matrix.shape[1]/max(matrix.shape)*20, matrix.shape[0]/max(matrix.shape)*20)
    size = 10,10
    fig, ax = plt.subplots(figsize=size)

    ax.imshow(matrix, interpolation='nearest', cmap=plt.cm.get_cmap('Greens'))

    #axes
    ax.xaxis.set_ticks([i for i in range(len(col_names))])
    ax.xaxis.set_ticklabels(col_names)
    ax.xaxis.set_ticks_position('top')

    ax.yaxis.set_ticks([i for i in range(len(row_names))])
    ax.yaxis.set_ticklabels(row_names)
    ax.yaxis.set_ticks_position('left')

    [l.set_rotation(90) for l in ax.xaxis.get_majorticklabels()]  #alternate is to use plt.setp but why do that?

    ax.set_title(title)

    fig.show()
    return fig


def main():

    sample_data = {
        'termid1':[],
        'termid2':[('nifid1','datasourcename1','indexable',1)],
        'termid3':[('nifid2','datasourcename2','indexable',2)],
        'termid4':[('nifid3','datasourcename3','indexable',3)],
        'termid5':[('nifid2','datasourcename2','indexable',4),('nifid3','datasourcename3','indexable',5)],
        'termid6':[('nifid1','datasourcename1','indexable',6),('nifid3','datasourcename3','indexable',7)],
        'termid7':[('nifid1','datasourcename1','indexable',8),('nifid2','datasourcename2','indexable',9)],
        'termid8':[('nifid1','datasourcename1','indexable',10),('nifid2','datasourcename2','indexable',11),('nifid3','datasourcename3','indexable',12)],
    }

    sample_source_nifids = [
        'nifid1',
        'nifid2',
        'nifid3',
        'nifid4',
    ]

    sample_ids = [  # shuffle these to get the order we want :)
        'termid1',
        'termid2',
        'termid3',
        'termid4',
        'termid5',
        'termid6',
        'termid7',
        'termid8',
    ]

    nifids = get_source_entity_nifids()

    #"""
    mat = construct_columns(sample_data, sample_ids, sample_source_nifids)
    f1 = display_heatmap(mat, sample_ids, sample_source_nifids, 'test')
    #embed()
    

    # anamotical regions
    #real_data = get_term_count_data('brain', 1, get_rel_id('has_part'), 'subject')
    real_data = 
    get_term_count_data('midbrain', 1, 'has_proper_part', 'subject')
    get_term_count_data('forebrain', 1, 'has_proper_part', 'subject')
    get_term_count_data('hindbrain', 1, 'has_proper_part', 'subject')
    real_data.update(
    # TODO sort on the hierarchy
    rownames = list(real_data.keys())
    mat2 = construct_columns(real_data, rownames, nifids)
    mat2_d = discretize(mat2)
    f2 = display_heatmap(mat2_d, rownames, nifids, 'brain partonomy')
    #"""

    #species FIXME need to figure out how to actually traverse the ncbi taxonomy
    species_data = get_term_count_data('eukaryota', 6, 'subClassOf', 'object')
    rownames3 = list(species_data.keys())
    mat3 = construct_columns(species_data, rownames3, nifids)
    mat3_d = discretize(mat3)  #FIXME in place ;_;
    f3 = display_heatmap(mat3_d, rownames3, nifids, 'species')
    embed()

    return 
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
