"""
    File for computing statistics of heatmaps.
    May eventually be merged into the explore interface.
"""
import requests
import numpy as np
import pylab as plt
from IPython import embed
from heatmaps.visualization import sCollapseToSrcName, applyCollapse
from heatmaps.services import LITERATURE_ID, TOTAL_TERM_ID, sortstuff, heatmap_service, summary_service
from heatmaps.scigraph_client import Graph

hms = heatmap_service(summary_service())
ss = sortstuff()
graph = Graph()

class hmStats:
    attrs = [
        'total term counts',
        'literature count',
        'arbitrary data source count',  # should just run the full matrix
        'term lenght',
        'term words',
        'term frequency',
        'depth in ontology hierarchy', 
        'number of relations in ontology',
        #'difference in rank between lit and freq',
    ]
    def __init__(self, hm_id, url = 'http://nif-services.neuinfo.org/servicesv1/v1/heatmaps/prov/'):
        self.hm_id = hm_id
        self.url = url + str(hm_id) + '.json'
        self.heatmap_data = requests.get(self.url).json()
        id_name_dict = {id_:name_tup[0] for id_, name_tup in hms.resources.items()}
        #self.id_name_dict[LITERATURE_ID] = ('Literature', 'Literature')
        id_coll_dict, self.id_name_dict = sCollapseToSrcName(self.heatmap_data[TOTAL_TERM_ID], id_name_dict)
        self.heatmap_data = applyCollapse(self.heatmap_data, id_coll_dict)  # must reassign
        cm1, sm1 = self.runStats()
        #cm2, sm2 = self.runStats(norm=True)
        #a = cm1 - cm2
        #b = sm1 - sm2
        #embed()
    
    def runStats(self, norm=False):
        totals = self.heatmap_data[TOTAL_TERM_ID]
        term_order = sorted(self.heatmap_data)
        term_order.remove(TOTAL_TERM_ID)
        src_idn = {s:s for s in totals}
        src_order, _ = ss.sort('frequency', self.heatmap_data, None, True, 1, src_idn)
        #embed()
        #return
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
                    if norm:
                        value = term_data[src] / totals[src]  # must normalize by total number of records!
                    else:
                        value = term_data[src]
                    if value:
                        freq += 1
                        total += value  # warning if using norm...
                    stats.append(value)
                else:
                    stats.append(0)

            #"""
            syns = [1]
            edges = [1, 2]
            """
            _, curie, _, syns = ss.term_server.term_id_expansion(term)

            if curie:
                curie = curie.replace('#', '%23')
                result = graph.getNeighbors(curie, depth=1, direction='BOTH')
                if not result:
                    print(term, curie)
                edges = result['edges']
            else:
                edges = []
            #"""
            
            stats.append(total)
            stats.append(freq)
            stats.append(len(term))
            stats.append(len(term.split(' ')))
            stats.append(len(syns))
            stats.append(len(edges))
            #stats.append(freq - term_data[LITERATURE_ID])

            term_stats.append(stats)#[::-1])

        stats_matrix = np.array(term_stats)
        #stats_order = [' '.join(hms.get_name_from_id(i)[0:2]) for i in src_order]
        stats_order = [self.id_name_dict[i] for i in src_order]  # FIXME we also need the indexable here for the x axis 
        print('num_views', len(stats_order))
        inset_names = ['total', 'freq', 'term length', 'term words', 'num syns', 'num edges']
        nstats2 = len(inset_names)
        stats_order.extend(inset_names)
        #print(stats_order)
        nstats = stats_matrix.shape[1]
        # compute pairwise corr between each pair of sources
        corrs = {}
        corr_mat = np.zeros((nstats, nstats))
        # massively inefficient
        for statCol1 in range(nstats):
            for statCol2 in range(statCol1, nstats):
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

        #figure code
        dpi = 600
        fig = plt.figure(figsize=(15,15), dpi=dpi)
        gs = plt.matplotlib.gridspec.GridSpec(1, 1, wspace=0)

        ax = fig.add_subplot(gs[0])
        ax.imshow(corr_mat, interpolation='nearest', cmap=plt.cm.get_cmap('seismic'), vmin=-1, vmax=1)

        ax.yaxis.set_ticks([i for i in range(nstats)])
        ax.yaxis.set_ticklabels(stats_order)
        ax.yaxis.set_ticks_position('right')
        [l.set_fontsize(5) for l in ax.yaxis.get_ticklabels()]

        ax.xaxis.set_ticks([i for i in range(nstats)])
        ax.xaxis.set_ticklabels(stats_order)
        ax.xaxis.set_ticks_position('top')
        [l.set_fontsize(5) for l in ax.xaxis.get_ticklabels()]
        [l.set_rotation(90) for l in ax.xaxis.get_majorticklabels()]

        ax.tick_params(direction='out', length=0, width=0)

        b = ax.get_position()
        x = .13
        y = .1125
        w = b.width
        h = b.height

        subax = fig.add_axes([x, y, w * .45, h * .45])
        subax.imshow(corr_mat[-nstats2:, -nstats2:], interpolation='nearest', cmap=plt.cm.get_cmap('seismic'), vmin=-1, vmax=1)

        subax.xaxis.set_ticks([i for i in range(nstats2)])
        subax.xaxis.set_ticklabels(inset_names)
        subax.xaxis.set_ticks_position('top')
        [l.set_rotation(90) for l in subax.xaxis.get_majorticklabels()]

        subax.yaxis.set_ticks([i for i in range(nstats2)])
        subax.yaxis.set_ticklabels(inset_names)
        subax.yaxis.set_ticks_position('right')

        subax.tick_params(direction='out', length=0, width=0)

        fig.savefig('/tmp/corrtest%s.png' % self.hm_id, bbox_inches='tight', pad_inches=.1, dpi=dpi)
        #for name in stats_order:
            #print(name)

        return corr_mat, stats_matrix

def main():
    url = 'http://localhost:5000/servicesv1/v1/heatmaps/prov/'
    hms40 = hmStats(40, url)
    #hms45 = hmStats(45, url)
    #hms46 = hmStats(46, url)
    #hms11 = hmStats(11, url)
    #hms13 = hmStats(13, url)
    #hms18 = hmStats(18, url)


if __name__ == '__main__':
    main()
