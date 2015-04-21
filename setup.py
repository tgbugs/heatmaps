from setuptools import setup

setup(
    name='heatmaps',
    version='0',
    description='heatmaps service for nif',
    long_description=' ',
    url='https://github.com/tgbugs/heatmaps',
    author='Tom Gillespie',
    author_email='tgbugs@gmail.com',
    license='MIT',
    classifiers=[],
    keywords='rest nif',
    #packages
    install_requires=[
        'lxml',
        'psycopg2',
        'requests',
        'ipython',
        'flask',
    ],
    #extras_require
    #package_data
    #data_files
    #entry_points
)
