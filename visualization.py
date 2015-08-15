from collections import defaultdict

def discretize(data_matrix):
    bins = [0,1,10,100]
    vals = [None,1,2,3]

    for lower, upper, val in zip(bins[:-1],bins[1:], vals[:-1]):
        data_matrix[ (data_matrix >= lower) * (data_matrix < upper) ] = val

    data_matrix[data_matrix >= bins[-1]] = vals[-1]

    return data_matrix

def sCollapseToSources(ids, names):
    pass

def sCollTemplate(ids, names):
    return 

def applyCollapse(heatmap_data, key_collections_dict, terms_axis=False): 
    """
        key_collections dict should have keys that are the values to be collapsed to
        given the heatmap data and an ordered list of key collections (so you can pair them up with
        the key you want them to converge to) collapse (sum) the data in each key collection
        note that the keys in the key collections must match those (and should probably come from)
        the keys in heatmap_data
    """
    output = {}
    if terms_axis:
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
                    new_counts_dict[new_source] += counts_dict[source]
            output[term] = new_counts_dict

    return output

def applyOrder():
    pass

def heatmap_data_processing(heatmap_data, termCollapse, sourceCollapse, termSort=sorted, sourceSort=sorted):
    """
        Given a heatmap_data object collapse and sort the terms and sources and return an 
    """


