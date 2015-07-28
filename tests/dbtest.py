#from services import heatmap_service, summary_service, term_service
# IMPORTS NOW BROKEN DUE TO RESTRUCTURING THE PROJECT WHEEEEE

def test(heatmap_service):
    # need to restructure how we actually do tests
    test_dict = dict(
        test_base = (
            'brain',
            'forebrain',
            'midbrain',

            'hindbrain',
            'hippocampus',
            'hypothalamus',
        ),
        test_subset = (
            'forebrain',
            'midbrain',
            'hindbrain',

            'hippocampus',
            'hypothalamus',
        ),
        test_set_2 = (
            'thalamus',
            'superior colliculus',
            'inferior olive',

            'pons',
            'cerebellum',
            'cortex',
        ),
        test_overlap = (
            'forebrain',
            'midbrain',
            'hindbrain',

            'pons',
            'cerebellum',
            'cortex',
        ),
    )

    try:
        ss = summary_service()
        ts = term_service()
        hs = heatmap_service(ss, ts)
        for test_terms in test_dict.values():
            hs.get_term_counts(*test_terms)
            hs.make_heatmap_data(*test_terms)
        embed()
    except:
        raise
    finally:
        hs.__exit__(hs,None,None,None)



