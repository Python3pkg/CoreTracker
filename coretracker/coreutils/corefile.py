from Bio.Alphabet import generic_nucleotide, generic_protein
from Bio.Seq import Seq
from Bio.SeqRecord import SeqRecord

class CoreFile:
    """Core File format for sequence alignment.
    This class enable parsing of CoreFile formats
    The CoreFile format is the following:
        >>geneID
        >specie1_ID
        ATCGTGATCCTAAGCTGATAGAAT
        >specie2_ID
        ATCGTGCAGATAGCTGATAGATGA
        ...
        >specie10_ID
        ATCTTAGTCGTAGCATAGTACTCG

        >>gene2_ID
        >specie1_ID
        ATGTGTCGTGCAGTCGT
        >specie1_ID
        ATGTGTCGTGCAGTCGT
        ...
    """

    def __init__(self, infile, alphabet=generic_protein):
        self.infile = infile
        if isinstance(alphabet, basestring):
            if alphabet.startswith('nuc'):
                self.alphabet = generic_nucleotide
            else:
                self.alphabet = generic_protein
        self.alphabet = alphabet
        self.sequences = self.parse_corefile(infile)

    def parse_corefile(self, infile):
        """Parse the corefile format"""
        core_dict = {}
        with open(infile, 'r') as handle:
            for gene, sequences in self._internal_coreparser(handle):
                core_dict[gene] = sequences
        return core_dict

    def _internal_coreparser(self, handle):
        """Internal function that actually parse the format using a handle"""
        while True:
            line = handle.readline()
            if line == "":
                return  # file end abruptly
            if line.startswith('>>'):
                # start looking only if we have the first line starting with
                # '>>'
                break
        genecounter = 0
        while True:
            if not line.startswith('>>'):
                raise ValueError(
                    'Records in corefile format should start with an >> followed by the name of the gene')
            genename = line[2:].rstrip()
            if not genename:
                genename = str(genecounter)
                genecounter += 1
            sequences = []
            line = handle.readline()
            while True:
                if not line:
                    break
                if line.startswith('>>'):
                    break
                if line.startswith('>'):
                    title = line[1:].rstrip()
                    lines = []
                    line = handle.readline()
                    while True:
                        if not line:
                            break
                        if line.startswith('>'):
                            break
                        lines.append(line.rstrip())
                        line = handle.readline()

                    sequence = "".join(lines).replace(
                        " ", "").replace("\r", "")
                    try:
                        first_word = title.split(None, 1)[0]
                    except IndexError:
                        assert not title, repr(title)
                        first_word = ""

                    sequences.append(SeqRecord(Seq(sequence, self.alphabet),
                                               id=first_word, name=first_word, description=title))
                else:
                    line = handle.readline()
            if sequences:
                yield genename, sequences
            if not line:
                return
        assert False, "We should return before this point"


    def write(self, outfile, sequences=None):
        """Save sequences into a file"""
        if sequences is None:
            sequences = self.sequences
        self.write_corefile(sequences)

    @classmethod
    def write_corefile(clc, sequences, outfile):
        with open(outfile, 'w') as OUT:
            for gene, sequence in sequences.items():
                OUT.write('>>%s\n' % gene)
                for seq in sequence:
                    OUT.write('>%s\n' % seq.name)
                    OUT.write('%s\n' % seq.seq._data)

    def __getitem__(self, id):
        """Return sequences for a gene"""
        return self.sequences[id]

    def get_sequences(self):
        """Return dict of sequences"""
        return self.sequences

    def items(self):
        """ iterate over the keys and values"""
        return self.sequences.items()