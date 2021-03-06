""" cnvpytor.vcf

class Vcf: reads SNP data from VCF file

"""
import pysam
import logging

_logger = logging.getLogger("cnvpytor.vcf")


class Vcf:

    def __init__(self, filename):
        """
        Opens VCF file, reads chromosome/sample names

        Parameters
        ----------
        filename : str
            Name of the VCF file.

        """
        self.filename = filename
        try:
            self.file = pysam.VariantFile(filename)
        except IOError:
            _logger.error("Problem opening file '%s'!" % filename)
            exit(0)
        except ValueError:
            _logger.error("Problem opening file '%s'!" % filename)
            exit(0)

        self.chrs = []
        self.samples = []
        self.lengths = {}
        if self.file:
            _logger.info("File: " + filename + " successfully open")
            self.chrs = list(self.file.header.contigs)
            self.samples = list(self.file.header.samples)
            for c in self.chrs:
                self.lengths[c] = self.file.header.contigs[c].length
            _logger.debug("Header contigs: %s" % ", ".join(self.chrs))
            _logger.debug("Header samples: %s" % ", ".join(self.samples))

    def get_chromosomes(self):
        """
        Get chromosome names.

        Returns
        -------
        chrs : list of str
            List of chromosome names from VCF header

        """
        return self.chrs

    def get_samples(self):
        """
        Get sample names.

        Returns
        -------
        samples : list of str
            List of sample names from VCF header

        """
        return self.samples

    def read_chromosome_snp(self, chr_name, sample='', ad_tag='AD', gt_tag='GT'):
        """
        Read SNP/indel data for given chromosome and sample.

        Parameters
        ----------
        chr_name : str
            Name of the chromosome.
        sample : str
            Name of the sample (first one if empty - default)

        Returns
        -------
        pos : list of int
            List of SNP positions.
        ref : list of str
            List of SNP reference base (A, T, G, C or .).
        alt : list of str
            List of SNP alternative base (A, T, G, C or .).
        nref : list of int
            Count of reads contains reference SNP.
        nalt : list of int
            Count of reads contains alternative SNP.
        gt : list of int
            List of genotypes (0 - "0/0", 1 - "0/1", 3- "1/1", 4 - "0|0" , 5 - "0|1", 6 - "1|0", 7 - "1|1").
        flag : list of int
            Binary flag: first bit 1 - SNP exists in database, second bit 1 - SNP in P region of strict mask.
        qual : list of int
            SNP quality (scale 0 - 255).

        """
        if sample == '':
            sample = self.samples[0]
        pos = []
        ref = []
        alt = []
        nref = []
        nalt = []
        gt = []
        flag = []
        qual = []
        alphabet = ['A', 'T', 'G', 'C', '.']
        try:
            for rec in self.file.fetch(chr_name):
                if "PASS" in rec.filter.keys() and rec.alts and len(rec.alts) == 1 and (
                        gt_tag in rec.samples[sample].keys()) and (
                        ad_tag in rec.samples[sample].keys()) and len(rec.samples[sample][gt_tag]) > 1 and len(
                    rec.samples[sample][ad_tag]) > 1:
                    if (len(rec.samples[sample][ad_tag]) > 1) and (rec.ref in alphabet) and (rec.alts[0] in alphabet):
                        pos.append(rec.pos)
                        ref.append(rec.ref)
                        alt.append(rec.alts[0])
                        flag.append(2)  # Assign P region as default (-mask_snps updates this flag)
                        if rec.qual == "." or rec.qual is None:
                            qual.append(0)
                        else:
                            qual.append(int(rec.qual / 10))  # divide QUAL by factor 10 and truncate to one byte
                        if qual[-1] > 255:
                            qual[-1] = 255
                        try:
                            nref.append(int(rec.samples[sample][ad_tag][0]))
                            nalt.append(int(rec.samples[sample][ad_tag][1]))
                        except ValueError:
                            nref.append(0)
                            nalt.append(0)
                        try:
                            UNICODE_EXISTS = bool(type(unicode))
                        except NameError:
                            unicode = str
                        if isinstance(rec.samples[sample][gt_tag], str) or isinstance(rec.samples[sample][gt_tag], unicode):
                            gt.append(int(rec.samples[sample][gt_tag][0]) * 2 + int(rec.samples[sample][gt_tag][2]))
                            if rec.samples[sample][gt_tag][1] == "|":
                                gt[-1] += 4
                        else:
                            gt.append(rec.samples[sample][gt_tag][0] * 2 + rec.samples[sample][gt_tag][1])
                            if rec.samples[sample].phased:
                                gt[-1] += 4
        except ValueError:
            _logger.error("Variant file reading problem. Probably index file is missing or corrupted.")
            exit(0)
        return pos, ref, alt, nref, nalt, gt, flag, qual

    def read_chromosome_snp_no_counts(self, chr_name, sample='', gt_tag='GT'):
        """
        Read SNP/indel data without counts (AD tag) for given chromosome and sample.

        Parameters
        ----------
        chr_name : str
            Name of the chromosome.
        sample : str
            Name of the sample (first one if empty - default)

        Returns
        -------
        pos : list of int
            List of SNP positions.
        ref : list of str
            List of SNP reference base (A, T, G, C or .).
        alt : list of str
            List of SNP alternative base (A, T, G, C or .).
        gt : list of int
            List of genotypes (0 - "0/0", 1 - "0/1", 3- "1/1", 4 - "0|0" , 5 - "0|1", 6 - "1|0", 7 - "1|1").
        flag : list of int
            Binary flag: first bit 1 - SNP exists in database, second bit 1 - SNP in P region of strict mask.
        qual : list of int
            SNP quality (scale 0 - 255).

        """
        if sample == '':
            sample = self.samples[0]
        pos = []
        ref = []
        alt = []
        gt = []
        flag = []
        qual = []
        alphabet = ['A', 'T', 'G', 'C', '.']
        try:
            for rec in self.file.fetch(chr_name):
                if "PASS" in rec.filter.keys() and rec.alts and len(rec.alts) == 1 and (
                        gt_tag in rec.samples[sample].keys()) and len(rec.samples[sample][gt_tag]) > 1:
                    if (rec.ref in alphabet) and (rec.alts[0] in alphabet):
                        pos.append(rec.pos)
                        ref.append(rec.ref)
                        alt.append(rec.alts[0])
                        flag.append(2)  # Assign P region as default (-mask_snps updates this flag)
                        if rec.qual == "." or rec.qual is None:
                            qual.append(0)
                        else:
                            qual.append(int(rec.qual / 10))  # divide QUAL by factor 10 and truncate to one byte
                        if qual[-1] > 255:
                            qual[-1] = 255
                        try:
                            UNICODE_EXISTS = bool(type(unicode))
                        except NameError:
                            unicode = str
                        if isinstance(rec.samples[sample][gt_tag], str) or isinstance(rec.samples[sample][gt_tag], unicode):
                            gt.append(int(rec.samples[sample][gt_tag][0]) * 2 + int(rec.samples[sample][gt_tag][2]))
                            if rec.samples[sample][gt_tag][1] == "|":
                                gt[-1] += 4
                        else:
                            gt.append(rec.samples[sample][gt_tag][0] * 2 + rec.samples[sample][gt_tag][1])
                            if rec.samples[sample].phased:
                                gt[-1] += 4

        except ValueError:
            _logger.error("Variant file reading problem. Probably index file is missing or corrupted.")
            exit(0)
        return pos, ref, alt, gt, flag, qual

    def read_all_snp(self, callback, sample='', ad_tag='AD', gt_tag='GT'):
        """
        Read SNP/indel data for given sample name.

        Parameters
        ----------
        callback : callable
            Function to call after read a chromosome:
            callback(chrom, pos, ref, alt, nref, nalt, gt, flag, qual)

        sample : str
            Name of the sample (first one if empty - default)

        Returns
        -------
        count : int
            Number of read chromosomes

        """
        if sample == '':
            sample = self.samples[0]
        pos = []
        ref = []
        alt = []
        nref = []
        nalt = []
        gt = []
        flag = []
        qual = []
        last_chrom = None
        count = 0
        alphabet = ['A', 'T', 'G', 'C', '.']

        try:
            for rec in self.file.fetch():
                if last_chrom is None:
                    last_chrom = rec.chrom
                if last_chrom != rec.chrom:
                    callback(last_chrom, pos, ref, alt, nref, nalt, gt, flag, qual)
                    pos = []
                    ref = []
                    alt = []
                    nref = []
                    nalt = []
                    gt = []
                    flag = []
                    qual = []
                    count += 1

                if "PASS" in rec.filter.keys() and rec.alts and len(rec.alts) == 1 and (
                        gt_tag in rec.samples[sample].keys()) and (
                        ad_tag in rec.samples[sample].keys()) and len(rec.samples[sample][gt_tag]) > 1 and len(
                    rec.samples[sample][ad_tag]) > 1:
                    if (len(rec.samples[sample][ad_tag]) > 1) and (rec.ref in alphabet) and (
                            rec.alts[0] in alphabet) and (rec.samples[sample][gt_tag][0] is not None) and (
                            rec.samples[sample][gt_tag][1] is not None):
                        pos.append(rec.pos)
                        ref.append(rec.ref)
                        alt.append(rec.alts[0])
                        flag.append(2)   # Assign P region as default (-mask_snps updates this flag)
                        if rec.qual == "." or rec.qual is None:
                            qual.append(0)
                        else:
                            qual.append(int(rec.qual / 10))  # divide QUAL by factor 10 and truncate to one byte
                        if qual[-1] > 255:
                            qual[-1] = 255
                        try:
                            nref.append(int(rec.samples[sample][ad_tag][0]))
                            nalt.append(int(rec.samples[sample][ad_tag][1]))
                        except ValueError:
                            nref.append(0)
                            nalt.append(0)
                        try:
                            UNICODE_EXISTS = bool(type(unicode))
                        except NameError:
                            unicode = str
                        if isinstance(rec.samples[sample][gt_tag], str) or isinstance(rec.samples[sample][gt_tag], unicode):
                            gt.append(int(rec.samples[sample][gt_tag][0]) * 2 + int(rec.samples[sample][gt_tag][2]))
                            if rec.samples[sample][gt_tag][1] == "|":
                                gt[-1] += 4
                        else:
                            gt.append(rec.samples[sample][gt_tag][0] * 2 + rec.samples[sample][gt_tag][1])
                            if rec.samples[sample].phased:
                                gt[-1] += 4

                last_chrom = rec.chrom
            if len(pos) > 0:
                callback(last_chrom, pos, ref, alt, nref, nalt, gt, flag, qual)
                count += 1
            return count
        except ValueError:
            _logger.error("Variant file reading problem.")
            exit(0)

    def read_all_snp_no_counts(self, callback, sample='', gt_tag='GT'):
        """
        Read SNP/indel data without counts (AD tag) for given sample name.

        Parameters
        ----------
        callback : callable
            Function to call after read a chromosome:
            callback(chrom, pos, ref, alt, gt, flag, qual)

        sample : str
            Name of the sample (first one if empty - default)

        Returns
        -------
        count : int
            Number of read chromosomes

        """
        if sample == '':
            sample = self.samples[0]
        pos = []
        ref = []
        alt = []
        gt = []
        flag = []
        qual = []
        last_chrom = None
        count = 0
        alphabet = ['A', 'T', 'G', 'C', '.']

        try:
            for rec in self.file.fetch():
                if last_chrom is None:
                    last_chrom = rec.chrom
                if last_chrom != rec.chrom:
                    callback(last_chrom, pos, ref, alt, gt, flag, qual)
                    pos = []
                    ref = []
                    alt = []
                    gt = []
                    flag = []
                    qual = []
                    count += 1

                if "PASS" in rec.filter.keys() and rec.alts and len(rec.alts) == 1 and (
                        gt_tag in rec.samples[sample].keys()) and len(rec.samples[sample][gt_tag]) > 1:
                    if (rec.ref in alphabet) and (rec.alts[0] in alphabet) and (
                            rec.samples[sample][gt_tag][0] is not None) and (rec.samples[sample][gt_tag][1] is not None):
                        pos.append(rec.pos)
                        ref.append(rec.ref)
                        alt.append(rec.alts[0])
                        flag.append(2)  # Assign P region as default (-mask_snps updates this flag)
                        if rec.qual == "." or rec.qual is None:
                            qual.append(0)
                        else:
                            qual.append(int(rec.qual / 10))  # divide QUAL by factor 10 and truncate to one byte
                        if qual[-1] > 255:
                            qual[-1] = 255
                        try:
                            UNICODE_EXISTS = bool(type(unicode))
                        except NameError:
                            unicode = str
                        if isinstance(rec.samples[sample][gt_tag], str) or isinstance(rec.samples[sample][gt_tag], unicode):
                            gt.append(int(rec.samples[sample][gt_tag][0]) * 2 + int(rec.samples[sample][gt_tag][2]))
                            if rec.samples[sample][gt_tag][1] == "|":
                                gt[-1] += 4
                        else:
                            gt.append(rec.samples[sample][gt_tag][0] * 2 + rec.samples[sample][gt_tag][1])
                            if rec.samples[sample].phased:
                                gt[-1] += 4

                last_chrom = rec.chrom
            if len(pos) > 0:
                callback(last_chrom, pos, ref, alt, gt, flag, qual)
                count += 1
            return count
        except ValueError:
            _logger.error("Variant file reading problem.")
            exit(0)
