from collections import defaultdict
import numpy as np

def discretize(data_matrix):
    bins = [0,1,10,100]
    vals = [None,1,2,3]

    for lower, upper, val in zip(bins[:-1],bins[1:], vals[:-1]):
        data_matrix[ (data_matrix >= lower) * (data_matrix < upper) ] = val

    data_matrix[data_matrix >= bins[-1]] = vals[-1]

    return data_matrix


def sCollapseToSrcId(keys, id_name_dict):
    """
        Collapse sources that have the same name, really base identifier
        but that mapping is a bit harder since I'd need to map the base id to 
        the name they have in common... maybe that is better?
    """
    
    key_collections_dict = defaultdict(set)
    new_id_name_dict = {}
    for key in keys:
        parent_key = key.rsplit('-',1)[0]
        key_collections_dict[parent_key].add(key)
        if parent_key not in new_id_name_dict:
            new_id_name_dict[parent_key] = id_name_dict[key]
        elif new_id_name_dict[parent_key] != id_name_dict[key]:
            raise NameError('Source names do not match! %s %s' %
                            (new_id_name_dict[parent_key], id_name_dict[key]))

    return dict(key_collections_dict), new_id_name_dict

def sCollTemplate(old_keys, *args):
    return key_collections_dict, new_id_name_dict

def applyCollapse(heatmap_data, key_collections_dict, term_axis=False): 
    """
        NOTE: keys not mapped will be DROPPED
        key_collections dict should have keys that are the values to be collapsed to
        given the heatmap data and an ordered list of key collections (so you can pair them up with
        the key you want them to converge to) collapse (sum) the data in each key collection
        note that the keys in the key collections must match those (and should probably come from)
        the keys in heatmap_data
    """
    #FIXME inefficient for single terms with no collapse
    output = {}
    if term_axis:
        for new_term, collection in key_collections_dict.items():
            new_term_counts = defaultdict(lambda :0)
            for term in collection:
                counts_dict = heatmap_data[term].items()
                for source, count in counts_dict:
                    new_term_counts[source] += count
            output[new_term] = dict(new_term_counts)
    else:  # default to collapse sources (the inner collection)
        for term, counts_dict in heatmap_data.items():
            new_counts_dict = defaultdict(lambda :0)
            for new_source, collection in key_collections_dict.items():
                for source in collection:
                    if source in counts_dict:
                        new_counts_dict[new_source] += counts_dict[source]
            output[term] = dict(new_counts_dict)

    return output

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
                        
def dict_to_matrix(tdict_sdict, term_id_order, src_id_order, TOTAL_TERM_ID):
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

def heatmap_data_processing(heatmap_data, termCollapse=None, sourceCollapse=None, termOrder=None, sourceOrder=None, TOTAL_KEY='federation_totals'):
    """
        Given a heatmap_data object collapse and sort the terms and sources and return an 
    """

    if termCollapse:
        heatmap_data = applyCollapse(heatmap_data, termCollapse, term_axis=True)

    if sourceCollapse:
        heatmap_data = applyCollapse(heatmap_data, sourceCollapse)

    termOrder = termSort(heatmap_data)
    sourceOrder = sourceSort(heatmap_data[TOTAL_KEY])
    
    return heatmap_data, termOrder, sourceOrder

def applyNames():
    """ Last step, make sure the identifier used has a name mapping! """


def main():
    test_data = {
        'term1':{'src1-1':1, 'src1-2':2, 'src2-1':3, 'src2-2':4},
        'term2':{'src2-1':1, 'src2-2':2, 'src3-1':3, 'src3-2':4},
        'term3':{'src3-1':1, 'src3-2':2, 'src4-1':3, 'src4-2':4},
        'total':{'src1-1':10, 'src1-2':11, 'src2-1':12, 'src2-2':13,
                 'src3-1':14, 'src3-2':15, 'src4-1':16, 'src4-2':17,
                 'src5-1':18, 'src5-2':19}
    } 

    test_src_id_name = {
        'src1-1':'Source 1',
        'src1-2':'Source 1',
        'src2-1':'Source 2',
        'src2-2':'Source 2',
        'src3-1':'Source 3',
        'src3-2':'Source 3',
        'src4-1':'Source 4',
        'src4-2':'Source 4',
        'src5-1':'Source 5',
        'src5-2':'Source 5',
    }

    test_term_id_name = {'term1':'bob', 'term2':'phil', 'term3':'ted', 'total':'total'}

    term_coll = {'term':{'term1', 'term2'}, 'term3':{'term3'},'total':{'total'}}
    term_names = {'term':'bob-phil', 'term3':'ted'}

    src_coll, src_names = sCollapseToSrcId(test_data['total'], test_src_id_name)

    dc, to, so = heatmap_data_processing(test_data, term_coll, src_coll, TOTAL_KEY='total')

    print(dc)
    print(to)
    print(so)


if __name__ == '__main__':
    main()
