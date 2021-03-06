[![Build Status](https://travis-ci.org/UdeM-LBIT/CoreTracker.svg?branch=master)](https://travis-ci.org/UdeM-LBIT/CoreTracker) [![PyPI version](https://badge.fury.io/py/CoreTracker.svg)](https://badge.fury.io/py/CoreTracker) [![Anaconda-Server Badge](https://anaconda.org/maclandrol/coretracker/badges/version.svg)](https://anaconda.org/maclandrol/coretracker) [![Anaconda-Server Badge](https://anaconda.org/maclandrol/coretracker/badges/installer/conda.svg)](https://conda.anaconda.org/maclandrol)
# CoreTracker
CoreTracker detects evidences of codon reassignment from the protein repertoire of a set
of genomes by successively applying different algorithms. It’s a filtering approach that
explore all possible reassignments in every genomes from the input set, and retain only the most promising one.

Detailled information about the package, installation and tutorials are available here ==> [http://udem-lbit.github.io/CoreTracker/](http://udem-lbit.github.io/CoreTracker/)



# Installation

First install the system dependencies which include `gfortran`, `PyQt4` `muscle`, `mafft` and `hmmer`. `PyQt4` also require `Sip` and `qt`. It's easier to install those two using distribution specific packages. You can now download the github project and install using `python setup.py install` or pip (`pip install coretracker`). I recommend setting a virtual environment through `virtualenv`.

Alternatively, you can also install it with `conda`, which is the easiest way : `conda install -c maclandrol coretracker=1.1.6`

# Basic Help
After installation, run `coretracker -h` for help.

An example of execution is :
``./coretracker.py -t speciestree.nw -p protein.ali -n nucsequences.core --gapfilter 0.4 --iccontent 0.3  --idfilter 0.5  --norefine --wdir outdir --params param.yml ``

Additionnal parameters could be set using the ``--params`` option. See the provided template (param.yml).
