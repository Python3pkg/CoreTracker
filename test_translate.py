#!/usr/bin/env python
from Bio import SeqIO
from coretracker.coreutils import SequenceLoader, CoreFile
import coretracker.coreutils.utils as utils
from Bio import AlignIO
import sys
import warnings
import os
import glob
import logging
import time
warnings.filterwarnings("ignore")
import argparse


# argument parser
parser = argparse.ArgumentParser(
    description='Translator, translate nucleotide alignment. You need to install hmmalign, muscle or mafft and biopython')
parser.add_argument('--wdir', '--outdir', dest="outdir",
                    default="trans_output", help="Working directory")
parser.add_argument('--nuc', '--input', '-n', dest='dnafile',
                    required=True, help="Dnafile input")
parser.add_argument('--gcode', type=int, default=1, dest='gcode',
                    help="Genetic code to use for translation. Default value is 1")
parser.add_argument('--prog', default="mafft", dest='prog', choices=[
                    'mafft', 'muscle'], help="Genetic code to use for translation. Default value is 1")
parser.add_argument('--align', dest='align', action='store_true',
                    help="Whether we should align or not")
parser.add_argument('--gapchar', dest='gapchar', default='-', help="Set default gap char")
parser.add_argument('--refine', dest='refine', action='store_true',
                    help="Whether we should refine the alignment with hmm")
parser.add_argument('--noclean', dest='noclean', action='store_false',
                    help="Whether we should clean unnecessary file or not")

parser.add_argument('--notrans', dest='notrans', action='store_true',
                        help="Whether we should attempt to translate or not. This overrule --align")

parser.add_argument('--filter', dest='filter', action='store_true',
                                        help="Filter nuc sequences to remove gene where frame-shifting occur")
parser.add_argument('--hmmdir', dest='hmmdir',
                    help="Link a directory with hmm files for alignment. Each hmmfile should be named in the following format : genename.hmm")

parser.add_argument('--verbose', '-v', dest='verbose', action='store_true',
                                        help="Print verbose (debug purpose)")


args = parser.parse_args()

if args.verbose:
    logging.basicConfig(level=logging.DEBUG)

utils.purge_directory(args.outdir)

core_inst = args.dnafile
gcode = args.gcode
align = args.align

prog = "mafft --auto"
if args.prog == 'muscle':
    prog = 'muscle'

hmmfiles = {}
if args.hmmdir:
    try:
        hfiles = glob.glob(os.path.join(args.hmmdir, '*'))
        for f in hfiles:
            genename = os.path.basename(f).split('.hmm')[0]
            hmmfiles[genename] = f
    except Exception as e:
        print e
        pass

if args.filter:
    # filter the sequences to remove genes where all the sequences do
    # not have a length that is a multiple of 3
    tmp_core_inst = CoreFile(core_inst, alphabet='nuc')
    # do not treat as missing sequence just remove the entire gene
    core_inst = {}
    gcount, total_gcount = 0, 0
    for gene, seqs in tmp_core_inst.items():
        good_data = []
        disp_data = []
        for seq in seqs:
            if len(seq.seq.ungap('-')) % 3 != 0:
                disp_data.append((seq.name, len(seq)))
            else:
                seq.seq = seq.seq.ungap('-')
                good_data.append(seq)
        total_gcount += 1
        if not disp_data:
            core_inst[gene] = good_data
            gcount += 1
            print("++> OK (%s)"%gene)
        else:
            print("--> Fail (%s), %d specs have frame-shifting : \n\t(%s)"%(gene, len(disp_data), ", ".join(["%s: %d, %d"%(x) for x in disp_data])))

    if not core_inst:
        sys.exit("After removing frameshifting, there isn't any remaining genes")

    print("======== Total of %d / %d genes rescued ========"%(gcount, total_gcount))

    # save new sequence file for coretracker later
    CoreFile.write_corefile(
        core_inst, os.path.join(args.outdir, "nuc.core"))
    # give time to read result
    time.sleep(2)

# proceed to translation if  here

if not args.notrans:
    translated_prot = SequenceLoader.translate(core_inst, gcode)
    alignment = {}
    if align:
        for (gene, seqs) in translated_prot.items():
            al = SequenceLoader._align(seqs, prog, None, 1.0, args.outdir)
            if args.refine:
                al = SequenceLoader._refine(al, 9999, args.outdir, loop=1,
                                      clean=args.noclean, hmmfile=hmmfiles.get(gene, None))
            alignment[gene] = al

        CoreFile.write_corefile(alignment, os.path.join(
            args.outdir, "prot_aligned.core"))
    else:
        CoreFile.write_corefile(
            translated_prot, os.path.join(args.outdir, "prot.core"))
