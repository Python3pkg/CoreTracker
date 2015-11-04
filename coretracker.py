#!/usr/bin/env python

from __future__ import division
import argparse
import collections
import itertools
import json
import numpy as np
import os
import random
import traceback
import subprocess

from multiprocessing import Pool

from collections import Counter

import warnings
warnings.filterwarnings("ignore") 
from Bio import AlignIO
from Bio import SeqIO
from Bio import SubsMat
from Bio.Align import AlignInfo
from Bio.codonalign import CodonAlignment
from Bio.Align import MultipleSeqAlignment
from Bio.Alphabet import generic_nucleotide
from Bio.Phylo.TreeConstruction import DistanceCalculator
from Bio.Seq import Seq
from Bio.codonalign.codonseq import _get_codon_list
from TreeLib import TreeClass
from ete3 import PhyloTree
from settings import *
from utils import *
from functools import partial
from shutil import copyfile


__author__ = "Emmanuel Noutahi"
__version__ = "0.1"
__email__ = "fmr.noutahi@umontreal.ca"
__license__ = "The MIT License (MIT)"



MAFFT_AUTO_COMMAND = ['linsi', 'ginsi', 'einsi', 'fftnsi', 'fftns', 'nwnsi', 'nwns', 'auto']


def testting_a_lot(args):


def coretracker(args):
    """Run coretracker on the argument list"""
      # Check mafft command input
    global OUTDIR
    global aa_letters
    run_alignment = False
    mafft_detail = get_argsname(args.__dict__, MAFFT_AUTO_COMMAND, prefix="--")
    mafft_cmd = "mafft "
    if(mafft_detail):
        run_alignment = True
        mafft_cmd += mafft_detail[0]
    if args.outdir:
        OUTDIR = args.outdir

    align_out = os.path.join(OUTDIR, 'alignment.fasta')
    
    # Manage fasta sequence input
    fasta_sequences = SeqIO.parse(args.seq, "fasta")
    record_dict = dict((seq.id, seq) for seq in fasta_sequences)
    seq_names = record_dict.keys()  # sequence id in the multi-alignment fasta file

    # load tree
    specietree = TreeClass(args.tree)
    leave_names = set(specietree.get_leaf_name())
    
    # check duplicated sequence name in the alignment file
    original_len = len(seq_names)

    # get dna to perform codon alignment
    dnaseq = SeqIO.parse(args.dnaseq, 'fasta',generic_nucleotide)
    dnaseq_ids = set([dna.id for dna in dnaseq])

    if len(set(seq_names)) != original_len or (set(seq_names) - leave_names) or (dnaseq_ids - leave_names):
        Output.error("Sequence not matching found, attempt to correct... ", "Warning")
        seq_names[:] = list(set(seq_names) & leave_names & dnaseq_ids)
        tmpseq = os.path.join(OUTDIR, "corr_seq_input.fasta")
        with open(tmpseq, 'w') as FASTAOUT:
            for seq in seq_names:
                FASTAOUT.write(record_dict[seq].format("fasta"))
        args.seq = tmpseq

    # prune tree to sequence list
    specietree.prune(seq_names)
    # set dna to sequence list
    dnaseq = [dna for dna in dnaseq if dna.id in seq_names]

    # debug list infos
    debug_infos = []

    # execute mafft    
    is_already_aligned = is_aligned(args.seq, 'fasta')

    if not (SKIP_ALIGNMENT and is_already_aligned):
        if not run_alignment:
            raise ValueError("Could not align sequences\nAlignment parameters not provided")
        else :
            # this is the case where we need to convert the tree to mafft tree before
            # Output stream setting
            mtoutput = Output(os.path.join(OUTDIR,"tree_mafft.nw"))
            # Convert tree to mafft format
            convert_tree_to_mafft(specietree, seq_names, mtoutput, args.scale)
            mtoutput.close()

            execute_mafft(mafft_cmd + " --treein %s %s > %s" %
                          (mtoutput.file, args.seq, align_out))

    else :
        copyfile(args.seq, align_out)

    # save tree
    specietree.write(outfile=os.path.join(OUTDIR,"phylotree.nw"))

    # Reload mafft alignment and filter alignment (remove gap positions and
    # positions not conserved)
    alignment = AlignIO.read(align_out, 'fasta', alphabet=alpha)
    record2seq = SeqIO.to_dict(alignment)
    debug_infos.append("Initial alignment length : %d"%alignment.get_alignment_length())
    
    # add this to keep trace of the gap filtered position 
    gap_filtered_position = []
    tt_filter_position = np.asarray(xrange(alignment.get_alignment_length()))

    if(args.excludegap): 
        alignment, gap_filtered_position = clean_alignment(
            alignment, threshold=(abs(args.excludegap) <= 1 or 0.01) * abs(args.excludegap))
        AlignIO.write(
            alignment, open(align_out + "_gapfilter", 'w'), 'fasta')

        debug_infos.append("Alignment length after removing gaps : %d"%alignment.get_alignment_length())

    # update list of position from the original alignment
    tt_filter_position = tt_filter_position[gap_filtered_position]

    # Compute expected frequency from the entire alignment and update at each
    # node
    armseq = alignment
    summary_info = AlignInfo.SummaryInfo(armseq)
    acc_rep_mat = SubsMat.SeqMat(summary_info.replacement_dictionary())
    # format of the acc_rep_mat:
    # {('A','C'): 10, ('C','H'): 12, ...}
    obs_freq_mat = SubsMat._build_obs_freq_mat(acc_rep_mat)
    # format of the obs_freq_matrix
    # same as the acc_rep_mat, but, we have frequency instead of count
    exp_freq_table = SubsMat._exp_freq_table_from_obs_freq(obs_freq_mat)
    # Not a dict of tuples anymore and it's obtained from the obs_freq_mat
    # {'A': 0.23, ...}
    # it's just the sum of replacement frequency for each aa.
    # if the two aa are differents, add half of the frequency
    # else add the frequency value
    # this unfortunaly assume that A-->C and C-->A have the same probability
    
    # Filter using the ic content
    if args.iccontent:
        align_info = AlignInfo.SummaryInfo(alignment)
        ic_content = align_info.information_content(e_freq_table=(exp_freq_table if USE_EXPECTED_FREQ_FOR_IC else None))
        max_val = max(align_info.ic_vector.values())* ((abs(args.iccontent) <= 1 or 0.01) * abs(args.iccontent))
        ic_pos = (np.asarray(align_info.ic_vector.values())>max_val).nonzero()
        filtered_alignment = filter_align_position(alignment, ic_pos[0])
        # update list of position based on change in ic_position
        tt_filter_position = tt_filter_position[ic_pos]
        AlignIO.write(filtered_alignment, open(align_out + "_ICfilter", 'w'), 'fasta')
        
        debug_infos.append("Alignment length after removing low IC columns : %d"%filtered_alignment.get_alignment_length())


    # Filter using the match percent per columns
    # Already enabled by default in the arguments list to filter 
    if(args.idfilter):
        filtered_alignment, position = filter_alignment(
            filtered_alignment, threshold=(abs(args.idfilter) <= 1 or 0.01) * abs(args.idfilter))
        AlignIO.write(
            filtered_alignment, open(align_out + "_IDfilter", 'w'), 'fasta')

        # update : remove position not conserved
        tt_filter_position = tt_filter_position[position]
        debug_infos.append("Alignment length after removing columns less conserved than threshold (%f) : %d"%(args.idfilter, filtered_alignment.get_alignment_length()))
    

    # Rmoving 100% match is done whether or not the others filters were applied
    filtered_alignment, position = filter_alignment(filtered_alignment, remove_identity=True, threshold=(
        abs(args.idfilter) <= 1 or 0.01) * abs(args.idfilter))
    AlignIO.write(filtered_alignment, open(align_out + "_filtered", 'w'), 'fasta')

    # update remove of identical column
    tt_filter_position = tt_filter_position[position]
    debug_infos.append("Alignment length after removing columns less conserved than threshold (%f) and 100%% identical : %d"%(args.idfilter, filtered_alignment.get_alignment_length()))

    if(EXCLUDE_AA):
        aa_letters = "".join([aa for aa in aa_letters if aa not in EXCLUDE_AA])

    print aa_letters
    # Compute sequence identity in global and filtered alignment
    number_seq = len(seq_names)
    matCalc = DistanceCalculator('identity')
    global_paired_distance = matCalc.get_distance(alignment)
    filtered_paired_distance = matCalc.get_distance(filtered_alignment)
    suspect_species = collections.defaultdict(Counter)
    genome_aa_freq = collections.defaultdict(dict)
   
    if args.debug :
        aa_json = collections.defaultdict(list)
        expected_freq = collections.defaultdict(float)
        count_max = -np.inf
        count_min = np.inf
        sim_json = collections.defaultdict(list)
         # alignment length
        af_length = filtered_alignment.get_alignment_length()
        ag_length = alignment.get_alignment_length()
        for i in xrange(number_seq):
            # Get aa count for each sequence
            count1 = Counter(alignment[i])
            count2 = Counter(filtered_alignment[i])
            for aa in aa_letters:

                expected_freq[aa_letters_1to3[aa]] = exp_freq_table[aa]
                global_val = count1[aa] / (ag_length * exp_freq_table[aa]) if count1[aa]>0 else 0.0
                filtered_val = count2[aa] / (af_length * exp_freq_table[aa]) if count1[aa]>0 else 0.0
                aa_json[aa_letters_1to3[aa]].append(
                    {'global': global_val, 'filtered': filtered_val, "species": seq_names[i]})
                count_max = max(filtered_val, global_val, count_max)
                count_min = min(filtered_val, global_val, count_min)
                genome_aa_freq[seq_names[i]][aa_letters_1to3[aa]] = global_val

            for j in xrange(i + 1):

                sim_json[seq_names[i]].append({"global": (1-global_paired_distance[seq_names[i], seq_names[j]])
                                              , "filtered":(1-filtered_paired_distance[seq_names[i], seq_names[j]]), "species": seq_names[j]})
                if i != j:
                    sim_json[seq_names[j]].append({"global": (1-global_paired_distance[seq_names[i], seq_names[j]])
                                              , "filtered": (1-filtered_paired_distance[seq_names[i], seq_names[j]]), "species": seq_names[i]})
                    
                # do not add identity to itself twice
        if(JSON_DUMP):
            with open(os.path.join(OUTDIR,"similarity.json"), "w") as outfile1:
                json.dump(sim_json, outfile1, indent=4)
            with open(os.path.join(OUTDIR, "aafrequency.json"), "w") as outfile2:
                json.dump({"AA": aa_json, "EXP": expected_freq, "MAX": count_max, "MIN" : count_min}, outfile2, indent=4)
        

    # for performance issues, it's better to make another loop to
    # get the data to plot the conservation of aa in each column
    # of the alignment

    consensus = get_consensus(filtered_alignment, AA_MAJORITY_THRESH)  
    # A little pretraitment to speed access to each record later
    global_consensus = get_consensus(alignment, AA_MAJORITY_THRESH)

    debug_infos.append("Filtered alignment consensus : \n%s\n"%consensus)

    aa2alignment = {}
    aa2identy_dict = {}
    for aa in aa_letters:
        cons_array = get_aa_filtered_alignment(consensus, aa)
        #print aa, "\n", cons_array, 
        if(cons_array):
            aa_filtered_alignment = filter_align_position(filtered_alignment, cons_array)
            aa2alignment[aa_letters_1to3[aa]] = aa_filtered_alignment
            aa2identy_dict[aa] =  matCalc.get_distance(aa_filtered_alignment)


    aa_shift_json = collections.defaultdict(list)
    for ind in itertools.combinations(xrange(number_seq), r=2):
        i, j = max(ind), min(ind)
        gpaired = 1 - global_paired_distance[seq_names[i], seq_names[j]]
        for aa in aa_letters:
            if aa in aa2identy_dict.keys():
                fpaired = 1 - aa2identy_dict[aa][seq_names[i], seq_names[j]]
                aa_shift_json[aa_letters_1to3[aa]].append({'global':gpaired , 'filtered': fpaired, "species": "%s||%s" % (seq_names[i], seq_names[j])})

    # dumping in json to reload with the web interface using d3.js
    if JSON_DUMP:
        with open(os.path.join(OUTDIR,"aause.json"), "w") as outfile3:
            json.dump(aa_shift_json, outfile3, indent=4)


    # transposing counter to dict and finding potential species 
    # that had a codon reassignment
    most_common = collections.defaultdict(list)
    for key, value in aa_shift_json.iteritems():
        for v in value:
            specs = v['species'].split('||')
            if(v['global']> v['filtered']):
                # Similarity higher in the global alignment
                # add the two species in the count
                suspect_species[key][specs[0]] = (suspect_species[key][specs[0]] or 0) + 1
                suspect_species[key][specs[1]] = (suspect_species[key][specs[1]] or 0) + 1

        # sort species list by the number of time it have a higher similarity in the global alignment
        common_list =  suspect_species[key].most_common()
        i = 0
        while i < len(common_list) and common_list[i][1] > FREQUENCY_THRESHOLD*len(seq_names):
            most_common[key].append(common_list[i])
            i += 1

    # At this step we have the most suspected species for each aa.
    # for each aa let's find the targeted aa
    aa2aa_rea = collections.defaultdict(dict)
    for key, sspecies in most_common.iteritems():
        aa_alignment = dict((x.id, x) for x in aa2alignment[key])
        
        one_letter_key = aa_letters_3to1[key]
        for (spec, count) in sspecies :
            suspected_aa = []
            for cur_aa in aa_alignment[spec]:
                print cur_aa
                if(cur_aa !='-' and cur_aa != one_letter_key):
                    suspected_aa.append(cur_aa)
                    try :
                        aa2aa_rea[one_letter_key][cur_aa].add(spec)
                    except KeyError:
                        aa2aa_rea[one_letter_key] = collections.defaultdict(set)
                        aa2aa_rea[one_letter_key][cur_aa].add(spec)

    # Parsimony fitch tree list
    fitch_tree = []

    codon_alignment, fcodon_alignment = codon_align(dnaseq, record2seq, gap_filtered_position, tt_filter_position)

    AlignIO.write(CodonAlignment(codon_alignment.values()), open(align_out + "_codon_align", 'w'), 'fasta')

    #codon_lst = []
    #for codon_aln in codon_alignment.values():
        #codon_lst.append(_get_codon_list(codon_aln.seq))

    for key1, dict2 in aa2aa_rea.iteritems():
    
        key1_alignment = aa2alignment[aa_letters_1to3[key1]]
        for key2, val in dict2.iteritems():
            gcodon_rea = CodonReaData((key1, key2), global_consensus, codon_alignment)
            fcodon_rea = CodonReaData((key1, key2), consensus, fcodon_alignment)
            counts = []
            t = specietree.copy("newick")
            n = NaiveFitch(t, val, aa_letters_1to3[key2], aa_letters_1to3[key1], (gcodon_rea, fcodon_rea))
            slist = n.get_species_list(LIMIT_TO_SUSPECTED_SPECIES)
            
            for s in slist:
                rec = record2seq[s]
                leaf = (n.tree&s)
                ori_count = 0
                try :
                    ori_count = len([y for x in key1_alignment for y in x if x.id==s and y!='-' and y==key2])
                except Exception:
                    #wtver happen, do nothing
                    pass

                leaf.add_features(count=0)
                leaf.add_features(filter_count=ori_count)
                leaf.add_features(lost=False)
                for position in range(len(rec)):
                    if global_consensus[position] == key1 \
                        and rec[position] == key2:
                        leaf.count+=1
                
                if('lost' in leaf.features and leaf.count < COUNT_THRESHOLD):
                    leaf.lost = True

                counts.append((s, str(leaf.count), str(leaf.filter_count), gcodon_rea.get_string(s, SHOW_MIXTE_CODONS), fcodon_rea.get_string(s, SHOW_MIXTE_CODONS)))
            debug_infos.append("\n\n Substitutions : " + key2 + " to "+ key1 + ": ")
            if(SHOW_MIXTE_CODONS):
                debug_infos.append("species\tglob_AA_count\tfilt_AA_count\tglob_reacodon_count\tglob_usedcodon_count\tglob_mixtecodon_count\tfilt_reacodon_count\tfilt_usedcodon_count\tfilt_mixtecodon_count\n" + "\n".join("\t".join(c) for c in counts))
            else:
                debug_infos.append("species\tglob_AA_count\tfilt_AA_count\tglob_reacodon_count\tglob_othercodon_count\tfilt_reacodon_count\tfilt_othercodon_count\n" + "\n".join("\t".join(c) for c in counts))

            if(n.is_valid()):
                n.render_tree(suffix=args.sfx)
                fitch_tree.append(n)

    if(args.debug and args.verbose>1):
        for line in debug_infos:
            print(line)
        print("After validating the ancestral state and checking in the global alignment, %d cases were found interesting"%len(fitch_tree))



if __name__ == '__main__':

    # argument parser
    parser = argparse.ArgumentParser(
        description='CoreTracker, A codon reassignment tracker newick tree format to mafft format')

    parser.add_argument(
        '--wdir', '--outdir', dest="outdir", help="Working directory")

    parser.add_argument('--version', action='version', version='%(prog)s 1.0')

    parser.add_argument('--excludegap', '--gap', type=float,  default=0.6, dest='excludegap',
                        help="Remove position with gap from the alignment, using excludegap as threshold. The absolute values are taken")
    
    parser.add_argument('--idfilter', '--id', type=float, default=0.8, dest='idfilter',
                        help="Conserve only position with at least idfilter residue identity")
    
    parser.add_argument('--iccontent', '--ic', type=float, default=0.5, dest='iccontent',
                        help="Shannon entropy threshold (default : 0.5 ). This will be used to discard column where IC < max(IC_INFO_VECTOR)*(IC_INFO_THRESHOLD/ 100.0)))")
    

    parser.add_argument(
        '--verbose', '-v', choices=[0,1,2], type=int, default=0, dest="verbose", help="Verbosity level")

    parser.add_argument(
        '--debug', action='store_true', dest="debug", help="Print debug infos")

    parser.add_argument(
        '--sfx', dest="sfx", default="", help="PDF rendering suffix to differentiate runs.")

    parser.add_argument('-t', '--intree', dest="tree",
                        help='Input specietree in newick format', required=True)
    
    parser.add_argument('-s', '--scale', type=float, default=1.0,
                        dest='scale', help="Scale to compute the branch format")

    parser.add_argument('--protseq', '--aa', '-p', '-a', dest='seq',
                        help="Protein sequence input in fasta format", required=True)

    parser.add_argument('--dnaseq', '--dna', '-n', dest='dnaseq',
                        help="Nucleotides sequences input in fasta format", required=True)
   

    mafft_group = parser.add_mutually_exclusive_group()
    mafft_group.add_argument('--linsi', dest='linsi', action='store_true',
                             help="L-INS-i (probably most accurate; recommended for <200 sequences; iterative refinement method incorporating local pairwise alignment information)")
    mafft_group.add_argument('--ginsi', dest='ginsi', action='store_true',
                             help="G-INS-i (suitable for sequences of similar lengths; recommended for <200 sequences; iterative refinement method incorporating global pairwise alignment information)")
    mafft_group.add_argument('--einsi', dest='einsi', action='store_true',
                             help="E-INS-i (suitable for sequences containing large unalignable regions; recommended for <200 sequences)")
    mafft_group.add_argument('--fftnsi', dest='fftnsi', action='store_true',
                             help="FFT-NS-i (iterative refinement method; two cycles only)")
    mafft_group.add_argument(
        '--fftns', dest='fftns', action='store_true', help="FFT-NS-2 (fast; progressive method)")
    mafft_group.add_argument('--nwnsi', dest='nwnsi', action='store_true',
                             help="NW-NS-i (iterative refinement method without FFT approximation; two cycles only)")
    mafft_group.add_argument('--nwns', dest='nwns', action='store_true',
                             help="NW-NS-2 (fast; progressive method without the FFT approximation)")
   
    mafft_group.add_argument(
        '--auto', dest='auto', action='store_true', help="If unsure which option to use, try this option")

    args = parser.parse_args()


    coretracker(args)