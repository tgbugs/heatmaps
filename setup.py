from setuptools import setup, find_packages

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
    packages = find_packages(exclude=['tests*', 'util*']),
    install_requires=[
        'docopt',
        'lxml',
        'numpy',
        'psycopg2',
        'requests',
        'ipython',
        'flask',
        'simplejson',
    ],
    #extras_require
    #package_data
    #data_files
    entry_points={
        'console_scripts': [
            'hmweb=heatmaps.webapp:main',
        ],
    },
)
