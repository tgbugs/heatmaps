"""
    File for computing statistics of heatmaps.
    May eventually be merged into the explore interface.
"""
import requests
import numpy as np
import pylab as plt
from IPython import embed
from heatmaps.services import LITERATURE_ID, TOTAL_TERM_ID, sortstuff
from heatmaps.scigraph_client import Graph

ss = sortstuff()
graph = Graph()

class hmStats:
    attrs = [
        'total term counts',
        'literature count',
        'arbitrary data source count',  # should just run the full matrix
        'term lenght',
        'term frequency',
        'depth in ontology hierarchy', 
        'number of relations in ontology',
    ]
    def __init__(self, hm_id, url = 'http://nif-services.neuinfo.org/servicesv1/v1/heatmaps/prov/'):
        self.hm_id = hm_id
        self.url = url + str(hm_id) + '.json'
        self.heatmap_data = requests.get(self.url).json()
        self.runStats()
    
    def runStats(self):
        totals = self.heatmap_data[TOTAL_TERM_ID]
        term_order = sorted(self.heatmap_data)
        term_order.remove(TOTAL_TERM_ID)
        src_idn = {s:s for s in totals}
        src_order, _ = ss.sort('frequency', self.heatmap_data, None, False, 1, src_idn)
        #src_order = sorted(totals)

        term_stats = []
        # construct a matrix of terms x stats
        for term in term_order:
            term_data = self.heatmap_data[term]
            total = 0
            freq = 0
            stats = []
            for src in src_order:
                if src in term_data:
                    value = term_data[src]
                    if value:
                        freq += 1
                        total += value
                    stats.append(value)
                else:
                    stats.append(0)

            _, curie, _, syns = ss.term_server.term_id_expansion(term)

            if curie:
                curie = curie.replace('#', '%23')
                result = graph.getNeighbors(curie, depth=1, direction='BOTH')
                if not result:
                    print(term, curie)
                edges = result['edges']
            else:
                edges = []
            
            stats.append(total)
            stats.append(freq)
            stats.append(len(term))
            stats.append(len(syns))
            stats.append(len(edges))

            term_stats.append(stats)#[::-1])

        stats_matrix = np.array(term_stats)
        stats_order = list(src_order)
        stats_order.extend(['total', 'freq', 'term length', 'nsyns', 'nedges'])
        #print(stats_order)
        nstats = stats_matrix.shape[1]

        # compute pairwise corr between each pair of sources
        corrs = {}
        corr_mat = np.empty((nstats, nstats))
        # massively inefficient
        for statCol1 in range(nstats):
            for statCol2 in range(nstats):
                n1 = stats_order[statCol1]
                n2 = stats_order[statCol2]
                name =  n1 + ' x ' + n2

                vec1 = stats_matrix[:,statCol1]
                vec2 = stats_matrix[:,statCol2]
                cc_mat = np.corrcoef(vec1, vec2)#[0]  # bad measure for this :/
                corr = cc_mat[0,1]
                if np.isnan(corr):  # happens when nums vs all zeros
                    #corr = 0
                    corr = -2  # something impossible

                corrs[name] = corr
                corr_mat[statCol1, statCol2] = corr

        np.nan_to_num(corr_mat)
        ranked = sorted([(k, v) for k, v in corrs.items()], key=lambda a: -a[1])
        fig = plt.figure(figsize=(15,15))
        gs = plt.matplotlib.gridspec.GridSpec(1, 1, wspace=0)
        ax = fig.add_subplot(gs[0])
        ax.imshow(corr_mat, interpolation='nearest', cmap=plt.cm.get_cmap('seismic'), vmin=-1, vmax=1)
        fig.savefig('/tmp/corrtest.png')
        for name in stats_order:
            print(name)

def main():
    url = 'http://localhost:5000/servicesv1/v1/heatmaps/prov/'
    hms40 = hmStats(40, url)


if __name__ == '__main__':
    main()
