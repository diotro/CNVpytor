""" cnvpytor.root

class Root: main CNVpytor class
"""
from .io import *
from .bam import Bam
from .vcf import Vcf
from .fasta import Fasta
from .genome import Genome
import numpy as np
import logging

_logger = logging.getLogger("cnvpytor.root")


class Root:

    def __init__(self, filename, max_cores=8):
        """
        Class constructor opens CNVpytor file. The class implements all core CNVpytor calculations.

        Parameters
        ----------
        filename : str
            CNVpytor filename
        max_cores : int
            Maximal number of cores used in parallel calculations

        """
        _logger.debug("App class init: filename '%s'; max cores %d." % (filename, max_cores))
        self.io = IO(filename)
        self.max_cores = max_cores
        self.io_gc = self.io
        self.io_mask = self.io
        if self.io.signal_exists(None, None, "reference genome") and self.io.signal_exists(None, None, "use reference"):
            rg_name = np.array(self.io.get_signal(None, None, "reference genome")).astype("str")[0]
            if rg_name in Genome.reference_genomes:
                rg_use = self.io.get_signal(None, None, "use reference")
                if "gc_file" in Genome.reference_genomes[rg_name] and rg_use[0] == 1:
                    _logger.debug("Using GC content from database for reference genome '%s'." % rg_name)
                    self.io_gc = IO(Genome.reference_genomes[rg_name]["gc_file"])
                if "mask_file" in Genome.reference_genomes[rg_name] and rg_use[1] == 1:
                    _logger.debug("Using strict mask from database for reference genome '%s'." % rg_name)
                    self.io_mask = IO(Genome.reference_genomes[rg_name]["mask_file"])

    def read_bam(self, bf, chroms):
        bamf = Bam(bf)
        if bamf.reference_genome:
            self.io.create_signal(None, None, "reference genome", np.array([np.string_(bamf.reference_genome)]))
            self.io.create_signal(None, None, "use reference", np.array([1, 1]).astype("uint8"))

        def read_chromosome(x):
            chrs, lens = x
            _logger.info("Reading data for chromosome %s with length %d" % (chrs, lens))
            l_rd_p, l_rd_u, l_his_read_frg = bamf.read_chromosome(chrs)
            return l_rd_p, l_rd_u, l_his_read_frg

        chrname, chrlen = bamf.get_chr_len()
        chr_len = [(c, l) for (c, l) in zip(chrname, chrlen) if len(chroms) == 0 or c in chroms]
        if self.max_cores == 1:
            count = 0
            cum_his_read_frg = None
            for cl in chr_len:
                rd_p, rd_u, his_read_frg = read_chromosome(cl)
                if not rd_p is None:
                    if cum_his_read_frg is None:
                        cum_his_read_frg = his_read_frg
                    else:
                        cum_his_read_frg += his_read_frg
                    self.io.save_rd(cl[0], rd_p, rd_u)
                    count += 1
            if not cum_his_read_frg is None:
                self.io.create_signal(None, None, "read frg dist", cum_his_read_frg)
            return count
        else:
            from .pool import parmap
            res = parmap(read_chromosome, chr_len, cores=self.max_cores)
            count = 0
            cum_his_read_frg = None
            for c, r in zip(chr_len, res):
                if not r[0] is None:
                    if cum_his_read_frg is None:
                        cum_his_read_frg = r[2]
                    else:
                        cum_his_read_frg += r[2]
                    self.io.save_rd(c[0], r[0], r[1])
                    count += 1
            if not cum_his_read_frg is None:
                self.io.create_signal(None, None, "read frg dist", cum_his_read_frg)
            return count

    def rd_stat(self, chroms=[], plot=True):
        rd_stat = []
        auto, sex, mt = False, False, False

        rd_gc_chromosomes = {}
        for c in self.io_gc.gc_chromosomes():
            rd_name = self.io.rd_chromosome_name(c)
            if not rd_name is None:
                rd_gc_chromosomes[rd_name] = c

        for c in rd_gc_chromosomes:
            if (len(chroms) == 0 or c in chroms):
                rd_p, rd_u = self.io.read_rd(c)
                max_bin = max(int(10 * np.mean(rd_u) + 1), int(10 * np.mean(rd_p) + 1))
                dist_p, bins = np.histogram(rd_p, bins=range(max_bin + 1))
                dist_u, bins = np.histogram(rd_u, bins=range(max_bin + 1))
                n_p, m_p, s_p = fit_normal(bins[1:-1], dist_p[1:])[0]
                n_u, m_u, s_u = fit_normal(bins[1:-1], dist_u[1:])[0]
                _logger.info(
                    "Chromosome '%s' stat - RD parity distribution gaussian fit:  %.2f +- %.2f" % (c, m_p, s_p))
                _logger.info(
                    "Chromosome '%s' stat - RD unique distribution gaussian fit:  %.2f +- %.2f" % (c, m_u, s_u))
                rd_stat.append((c, m_p, s_p, m_u, s_u))
                auto = auto or Genome.is_autosome(c)
                sex = sex or Genome.is_sex_chrom(c)
                mt = mt or Genome.is_mt_chrom(c)

        if auto:
            max_bin_auto = int(
                max(map(lambda x: 5 * x[1] + 5 * x[2], filter(lambda x: Genome.is_autosome(x[0]), rd_stat))))
            _logger.debug("Max RD for autosomes calculated: %d" % max_bin_auto)
            dist_p_auto = np.zeros(max_bin_auto)
            dist_u_auto = np.zeros(max_bin_auto)
            dist_p_gc_auto = np.zeros((max_bin_auto, 101))
            bins_auto = range(max_bin_auto + 1)
        if sex:
            max_bin_sex = int(
                max(map(lambda x: 5 * x[1] + 5 * x[2], filter(lambda x: Genome.is_sex_chrom(x[0]), rd_stat))))
            _logger.debug("Max RD for sex chromosomes calculated: %d" % max_bin_sex)
            dist_p_sex = np.zeros(max_bin_sex)
            dist_u_sex = np.zeros(max_bin_sex)
            dist_p_gc_sex = np.zeros((max_bin_sex, 101))
            bins_sex = range(max_bin_sex + 1)

        if mt:
            max_bin_mt = int(
                max(map(lambda x: 5 * x[1] + 5 * x[2], filter(lambda x: Genome.is_mt_chrom(x[0]), rd_stat))))
            _logger.debug("Max RD for mitochondria calculated: %d" % max_bin_mt)
            bin_size_mt = max_bin_mt // 100
            bins_mt = range(0, max_bin_mt // bin_size_mt * bin_size_mt + bin_size_mt, bin_size_mt)
            n_bins_mt = len(bins_mt) - 1
            _logger.debug("Using %d bin size, %d bins for mitochondria chromosome." % (bin_size_mt, n_bins_mt))
            dist_p_mt = np.zeros(n_bins_mt)
            dist_u_mt = np.zeros(n_bins_mt)
            dist_p_gc_mt = np.zeros((n_bins_mt, 101))

        for c in rd_gc_chromosomes:
            if len(chroms) == 0 or c in chroms:
                _logger.info("Chromosome '%s' stat " % c)
                rd_p, rd_u = self.io.read_rd(c)
                if Genome.is_autosome(c):
                    dist_p, bins = np.histogram(rd_p, bins=bins_auto)
                    dist_u, bins = np.histogram(rd_u, bins=bins_auto)
                    gcat = self.io_gc.get_signal(rd_gc_chromosomes[c], None, "GC/AT")
                    gcp = gcp_decompress(gcat)
                    dist_p_gc, xbins, ybins = np.histogram2d(rd_p, gcp, bins=(bins_auto, range(102)))
                    dist_p_auto += dist_p
                    dist_u_auto += dist_u
                    dist_p_gc_auto += dist_p_gc
                elif Genome.is_sex_chrom(c):
                    dist_p, bins = np.histogram(rd_p, bins=bins_sex)
                    dist_u, bins = np.histogram(rd_u, bins=bins_sex)
                    gcat = self.io_gc.get_signal(rd_gc_chromosomes[c], None, "GC/AT")
                    gcp = gcp_decompress(gcat)
                    dist_p_gc, xbins, ybins = np.histogram2d(rd_p, gcp, bins=(bins_sex, range(102)))
                    dist_p_sex += dist_p
                    dist_u_sex += dist_u
                    dist_p_gc_sex += dist_p_gc
                elif Genome.is_mt_chrom(c):
                    dist_p, bins = np.histogram(rd_p, bins=bins_mt)
                    dist_u, bins = np.histogram(rd_u, bins=bins_mt)
                    gcat = self.io_gc.get_signal(rd_gc_chromosomes[c], None, "GC/AT")
                    gcp = gcp_decompress(gcat)
                    dist_p_gc, xbins, ybins = np.histogram2d(rd_p, gcp, bins=(bins_mt, range(102)))
                    dist_p_mt += dist_p
                    dist_u_mt += dist_u
                    dist_p_gc_mt += dist_p_gc

        if auto:
            n_auto, m_auto, s_auto = fit_normal(np.array(bins_auto[1:-1]), dist_p_auto[1:])[0]
            _logger.info("Autosomes stat - RD parity distribution gaussian fit:  %.2f +- %.2f" % (m_auto, s_auto))
            stat_auto = np.array([max_bin_auto, 1, max_bin_auto, n_auto, m_auto, s_auto])
            self.io.create_signal(None, 100, "RD p dist", dist_p_auto, flags=FLAG_AUTO)
            self.io.create_signal(None, 100, "RD u dist", dist_u_auto, flags=FLAG_AUTO)
            self.io.create_signal(None, 100, "RD GC dist", dist_p_gc_auto, flags=FLAG_AUTO)
            self.io.create_signal(None, 100, "RD stat", stat_auto, flags=FLAG_AUTO)
            gc_corr_auto = calculate_gc_correction(dist_p_gc_auto, m_auto, s_auto)
            self.io.create_signal(None, 100, "GC corr", gc_corr_auto, flags=FLAG_AUTO)

        if sex:
            n_sex, m_sex, s_sex = fit_normal(np.array(bins_sex[1:-1]), dist_p_sex[1:])[0]
            _logger.info("Sex chromosomes stat - RD parity distribution gaussian fit:  %.2f +- %.2f" % (m_sex, s_sex))
            stat_sex = np.array([max_bin_sex, 1, max_bin_sex, n_sex, m_sex, s_sex])
            self.io.create_signal(None, 100, "RD p dist", dist_p_sex, flags=FLAG_SEX)
            self.io.create_signal(None, 100, "RD u dist", dist_u_sex, flags=FLAG_SEX)
            self.io.create_signal(None, 100, "RD GC dist", dist_p_gc_sex, flags=FLAG_SEX)
            self.io.create_signal(None, 100, "RD stat", stat_sex, flags=FLAG_SEX)
            gc_corr_sex = calculate_gc_correction(dist_p_gc_sex, m_sex, s_sex)
            self.io.create_signal(None, 100, "GC corr", gc_corr_sex, flags=FLAG_SEX)

        if mt:
            n_mt, m_mt, s_mt = fit_normal(np.array(bins_mt[1:-1]), dist_p_mt[1:])[0]
            _logger.info("Mitochondria stat - RD parity distribution gaussian fit:  %.2f +- %.2f" % (m_mt, s_mt))
            if auto:
                _logger.info("Mitochondria stat - number of mitochondria per cell:  %.2f +- %.2f" % (
                    2. * m_mt / m_auto, 2. * s_mt / m_auto + s_auto * m_mt / (m_auto * m_auto)))
            stat_mt = np.array([max_bin_mt, bin_size_mt, n_bins_mt, n_mt, m_mt, s_mt])
            self.io.create_signal(None, 100, "RD p dist", dist_p_mt, flags=FLAG_MT)
            self.io.create_signal(None, 100, "RD u dist", dist_u_mt, flags=FLAG_MT)
            self.io.create_signal(None, 100, "RD GC dist", dist_p_gc_mt, flags=FLAG_MT)
            self.io.create_signal(None, 100, "RD stat", stat_mt, flags=FLAG_MT)
            gc_corr_mt = calculate_gc_correction(dist_p_gc_mt, m_mt, s_mt, bin_size_mt)
            self.io.create_signal(None, 100, "GC corr", gc_corr_mt, flags=FLAG_MT)

    def read_vcf(self, vcf_file, chroms, sample=''):
        vcff = Vcf(vcf_file)
        chrs = [c for c in vcff.get_chromosomes() if len(chroms) == 0 or c in chroms]
        count = 0
        for c in chrs:
            _logger.info("Reading variant data for chromosome %s" % c)
            pos, ref, alt, nref, nalt, gt, flag, qual = vcff.read_chromosome_snp(c, sample)

            if not pos is None and len(pos) > 0:
                self.io.save_snp(c, pos, ref, alt, nref, nalt, gt, flag, qual)
                count += 1
        return count

    def rd(self, bamfiles, chroms=[]):
        """ Read chromosomes from bam/sam/cram file(s) and store in .cnvnator file
                Arguments:
                    * list of bam file names
                    * list of chromosome names
        """
        hm = 0
        for bf in bamfiles:
            hm += self.read_bam(bf, chroms)

        if self.io.signal_exists(None, None, "reference genome"):
            rg_name = np.array(self.io.get_signal(None, None, "reference genome")).astype("str")[0]
            if "mask_file" in Genome.reference_genomes[rg_name]:
                _logger.info("Strict mask for reference genome '%s' found in database." % rg_name)
                self.io_mask = IO(Genome.reference_genomes[rg_name]["mask_file"])
            if "gc_file" in Genome.reference_genomes[rg_name]:
                _logger.info("GC content for reference genome '%s' found in database." % rg_name)
                self.io_gc = IO(Genome.reference_genomes[rg_name]["gc_file"])
                self.rd_stat()

        return hm

    def vcf(self, vcf_files, chroms=[], sample=''):
        """ Read SNP data from variant file(s) and store in .cnvnator file
                Arguments:
                    * list of variant file names
                    * list of chromosome names
        """
        hm = 0
        for vcf_file in vcf_files:
            hm += self.read_vcf(vcf_file, chroms, sample)
        return hm

    def pileup_bam(self, bamfile, chroms, pos, ref, alt, nref, nalt):
        """
        TODO:

        Parameters
        ----------
        bamfile
        chroms

        """
        _logger.info("Calculating pileup from bam file '%s'." % bamfile)
        bamf = Bam(bamfile)

        def pileup_chromosome(x):
            c, l, snpc = x
            _logger.info("Pileup chromosome %s with length %d" % (c, l))
            return bamf.pileup(c, pos[snpc], ref[snpc], alt[snpc])

        chrname, chrlen = bamf.get_chr_len()
        chr_len = [(c, l, self.io.snp_chromosome_name(c)) for (c, l) in zip(chrname, chrlen) if
                   self.io.snp_chromosome_name(c) in chroms]

        if self.max_cores == 1:
            for cl in chr_len:
                r = pileup_chromosome(cl)
                nref[cl[2]] = [x + y for x, y in zip(nref[cl[2]], r[0])]
                nalt[cl[2]] = [x + y for x, y in zip(nalt[cl[2]], r[1])]

        else:
            from .pool import parmap
            res = parmap(pileup_chromosome, chr_len, cores=self.max_cores)
            for cl, r in zip(chr_len, res):
                nref[cl[2]] = [x + y for x, y in zip(nref[cl[2]], r[0])]
                nalt[cl[2]] = [x + y for x, y in zip(nalt[cl[2]], r[1])]

    def pileup(self, bamfiles, chroms=[]):
        """
        Read bam/sam/cram file(s) and pile up SNP counts at positions imported with vcf(vcf_files, ...) method

        Parameters
        ----------
        bamfiles : list of str
            Bam files.
        """
        chrs = [c for c in self.io.snp_chromosomes() if (len(chroms) == 0 or c in chroms)]

        pos, ref, alt, nref, nalt, gt, flag, qual = {}, {}, {}, {}, {}, {}, {}, {}
        for c in chrs:
            _logger.info("Decompressing and setting all SNP counts to zero for chromosome '%s'." % c)
            pos[c], ref[c], alt[c], nref[c], nalt[c], gt[c], flag[c], qual[c] = self.io.read_snp(c)
            nref[c] = [0] * len(nref[c])
            nalt[c] = [0] * len(nalt[c])
        for bf in bamfiles:
            self.pileup_bam(bf, chrs, pos, ref, alt, nref, nalt)

        for c in chrs:
            _logger.info("Saving SNP data for chromosome '%s' in file '%s'." % (c, self.io.filename))
            self.io.save_snp(c, pos[c], ref[c], alt[c], nref[c], nalt[c], gt[c], flag[c], qual[c])

    def gc(self, filename, chroms=[], make_gc_genome_file=False):
        """ Read GC content from reference fasta file and store in .cnvnator file
                Arguments:
                    * FASTA filename
                    * list of chromosome names
        """
        fasta = Fasta(filename)
        chrname, chrlen = fasta.get_chr_len()
        chr_len_rdn = []
        if make_gc_genome_file:
            _logger.debug("GC data for all reference genome contigs will be read and stored in cnvnator file.")
            for (c, l) in zip(chrname, chrlen):
                chr_len_rdn.append((c, l, c))
        else:
            for (c, l) in zip(chrname, chrlen):
                rd_name = self.io.rd_chromosome_name(c)
                if len(chroms) == 0 or (rd_name in chroms) or (c in chroms):
                    if rd_name is None:
                        _logger.debug("Not found RD signal for chromosome '%s'. Skipping..." % c)
                    else:
                        _logger.debug("Found RD signal for chromosome '%s' with name '%s'." % (c, rd_name))
                        chr_len_rdn.append((c, l, rd_name))
        count = 0
        for c, l, rdn in chr_len_rdn:
            _logger.info("Reading data for chromosome '%s' with length %d" % (c, l))
            gc, at = fasta.read_chromosome_gc(c)
            if not gc is None:
                self.io.create_signal(rdn, None, "GC/AT", gc_at_compress(gc, at))
                count += 1
                _logger.info("GC data for chromosome '%s' saved in file '%s'." % (rdn, self.io.filename))
        if count > 0:
            _logger.info("Running RD statistics on chromosomes with imported GC data.")
            self.rd_stat()
        return count

    def copy_gc(self, filename, chroms=[]):
        """ Copy GC content from another cnvnator file
                Arguments:
                    * cnvnator filename
                    * list of chromosome names
        """
        io_src = IO(filename)
        chr_rdn = []
        for c in io_src.chromosomes_with_signal(None, "GC/AT"):
            rd_name = self.io.rd_chromosome_name(c)
            if len(chroms) == 0 or (rd_name in chroms) or (c in chroms):
                if rd_name is None:
                    _logger.debug("Not found RD signal for chromosome '%s'. Skipping..." % c)
                else:
                    _logger.debug("Found RD signal for chromosome '%s' with name '%s'." % (c, rd_name))
                    chr_rdn.append((c, rd_name))
        count = 0
        for c, rdn in chr_rdn:
            _logger.info(
                "Copying GC data for chromosome '%s' from file '%s' in file '%s'." % (c, filename, self.io.filename))
            self.io.create_signal(rdn, None, "GC/AT", io_src.get_signal(c, None, "GC/AT").astype(dtype="uint8"))
        return count

    def mask(self, filename, chroms=[], make_mask_genome_file=False):
        """ Read strict mask fasta file and store in .cnvnator file
                Arguments:
                    * FASTA filename
                    * list of chromosome names
        """
        fasta = Fasta(filename)
        chrname, chrlen = fasta.get_chr_len()
        chr_len_rdn = []
        if make_mask_genome_file:
            _logger.debug("Strict mask data for all reference genome contigs will be read and stored in cnvnator file.")
            for (c, l) in zip(chrname, chrlen):
                chr_len_rdn.append((c, l, c))
        else:
            for (c, l) in zip(chrname, chrlen):
                rd_name = self.io.rd_chromosome_name(c)
                snp_name = self.io.snp_chromosome_name(c)
                if len(chroms) == 0 or (rd_name in chroms) or (snp_name in chroms) or (c in chroms):
                    if (rd_name is None) and (snp_name is None):
                        _logger.debug("Not found RD or SNP signal for chromosome '%s'. Skipping..." % c)
                    elif (rd_name is None):
                        _logger.debug("Found SNP signal for chromosome '%s' with name '%s'." % (c, snp_name))
                        chr_len_rdn.append((c, l, snp_name))
                    else:
                        _logger.debug("Found RD signal for chromosome '%s' with name '%s'." % (c, rd_name))
                        chr_len_rdn.append((c, l, rd_name))
        count = 0
        for c, l, rdn in chr_len_rdn:
            _logger.info("Reading data for chromosome '%s' with length %d" % (c, l))
            mask = fasta.read_chromosome_mask_p_regions(c)
            if not mask is None:
                self.io.create_signal(rdn, None, "mask", mask_compress(mask))
                count += 1
                _logger.info("Strict mask data for chromosome '%s' saved in file '%s'." % (rdn, self.io.filename))
        return count

    def copy_mask(self, filename, chroms=[]):
        """ Copy strict mask data from another cnvnator file
                Arguments:
                    * cnvnator filename
                    * list of chromosome names
        """
        io_src = IO(filename)
        chr_rdn = []
        for c in io_src.chromosomes_with_signal(None, "mask"):
            rd_name = self.io.rd_chromosome_name(c)
            snp_name = self.snp_chromosome_name(c)
            if len(chroms) == 0 or (rd_name in chroms) or (snp_name in chroms) or (c in chroms):
                if (rd_name is None) and (snp_name is None):
                    _logger.debug("Not found RD or SNP signal for chromosome '%s'. Skipping..." % c)
                elif (rd_name is None):
                    _logger.debug("Found SNP signal for chromosome '%s' with name '%s'." % (c, snp_name))
                    chr_rdn.append((c, snp_name))
                else:
                    _logger.debug("Found RD signal for chromosome '%s' with name '%s'." % (c, rd_name))
                    chr_rdn.append((c, rd_name))
        count = 0
        for c, rdn in chr_rdn:
            _logger.info(
                "Copying strict mask data for chromosome '%s' from file '%s' in file '%s'." % (
                    c, filename, self.io.filename))
            self.io.create_signal(rdn, None, "mask", io_src.get_signal(c, None, "mask").astype(dtype="uint32"))
        return count

    def set_reference_genome(self, rg):
        """ Manually sets reference genome.

        Parameters
        ----------
        rg: str
            Name of reference genome

        Returns
        -------
            True if genome exists in database

        """
        if rg in Genome.reference_genomes:
            self.io.create_signal(None, None, "reference genome", np.array([np.string_(rg)]))
            self.io.create_signal(None, None, "use reference", np.array([1, 1]).astype("uint8"))


    def calculate_histograms(self, bin_sizes, chroms=[]):

        rd_gc_chromosomes = {}
        for c in self.io_gc.gc_chromosomes():
            rd_name = self.io.rd_chromosome_name(c)
            if not rd_name is None and (len(chroms) == 0 or (rd_name in chroms) or (c in chroms)):
                rd_gc_chromosomes[rd_name] = c

        rd_mask_chromosomes = {}
        for c in self.io_mask.mask_chromosomes():
            rd_name = self.io.rd_chromosome_name(c)
            if not rd_name is None and (len(chroms) == 0 or (rd_name in chroms) or (c in chroms)):
                rd_mask_chromosomes[rd_name] = c

        for bin_size in bin_sizes:
            his_stat = []
            auto, sex, mt = False, False, False
            bin_ratio = bin_size // 100

            for c in self.io.rd_chromosomes():
                if c in rd_gc_chromosomes:
                    _logger.info("Calculating histograms using bin size %d for chromosome '%s'." % (bin_size, c))
                    flag = FLAG_MT if Genome.is_mt_chrom(c) else FLAG_SEX if Genome.is_sex_chrom(c) else FLAG_AUTO
                    rd_p, rd_u = self.io.read_rd(c)
                    his_p = np.concatenate(
                        (rd_p, np.zeros(bin_ratio - len(rd_p) + (len(rd_p) // bin_ratio * bin_ratio))))
                    his_p.resize((len(his_p) // bin_ratio, bin_ratio))
                    his_p = his_p.sum(axis=1)
                    his_u = np.concatenate(
                        (rd_u, np.zeros(bin_ratio - len(rd_u) + (len(rd_u) // bin_ratio * bin_ratio))))
                    his_u.resize((len(his_u) // bin_ratio, bin_ratio))
                    his_u = his_u.sum(axis=1)
                    self.io.create_signal(c, bin_size, "RD", his_p)
                    self.io.create_signal(c, bin_size, "RD unique", his_u)

                    max_bin = max(int(10 * np.mean(his_u) + 1), int(10 * np.mean(his_p) + 1))
                    rd_bin_size = max_bin // 10000
                    if rd_bin_size == 0:
                        rd_bin_size = 1
                    rd_bins = range(0, max_bin // rd_bin_size * rd_bin_size + rd_bin_size, rd_bin_size)
                    dist_p, bins = np.histogram(his_p, bins=rd_bins)
                    dist_u, bins = np.histogram(his_u, bins=rd_bins)
                    n_p, m_p, s_p = fit_normal(bins[1:-1], dist_p[1:])[0]
                    n_u, m_u, s_u = fit_normal(bins[1:-1], dist_u[1:])[0]
                    _logger.info(
                        "Chromosome '%s' bin size %d stat - RD parity distribution gaussian fit:  %.2f +- %.2f" % (
                            c, bin_size, m_p, s_p))
                    _logger.info(
                        "Chromosome '%s' bin size %d stat - RD unique distribution gaussian fit:  %.2f +- %.2f" % (
                            c, bin_size, m_u, s_u))
                    his_stat.append((c, m_p, s_p, m_u, s_u))
                    auto = auto or Genome.is_autosome(c)
                    sex = sex or Genome.is_sex_chrom(c)
                    mt = mt or Genome.is_mt_chrom(c)

            if auto:
                max_bin_auto = int(
                    max(map(lambda x: 5 * x[1] + 5 * x[2], filter(lambda x: Genome.is_autosome(x[0]), his_stat))))
                _logger.debug("Max RD for autosome histograms calculated: %d." % max_bin_auto)
                bin_size_auto = max_bin_auto // 1000
                if bin_size_auto == 0:
                    bin_size_auto = 1
                bins_auto = range(0, max_bin_auto // bin_size_auto * bin_size_auto + bin_size_auto, bin_size_auto)
                n_bins_auto = len(bins_auto) - 1
                _logger.debug(
                    "Using %d RD bin size, %d bins for autosome RD - GC distributions." % (bin_size_auto, n_bins_auto))
                dist_p_auto = np.zeros(n_bins_auto)
                dist_u_auto = np.zeros(n_bins_auto)
                dist_p_gc_auto = np.zeros((n_bins_auto, 101))

            if sex:
                max_bin_sex = int(
                    max(map(lambda x: 5 * x[1] + 5 * x[2], filter(lambda x: Genome.is_sex_chrom(x[0]), his_stat))))
                _logger.debug("Max RD for sex chromosome histograms calculated: %d." % max_bin_sex)
                bin_size_sex = max_bin_sex // 1000
                if bin_size_sex == 0:
                    bin_size_sex = 1
                bins_sex = range(0, max_bin_sex // bin_size_sex * bin_size_sex + bin_size_sex, bin_size_sex)
                n_bins_sex = len(bins_sex) - 1
                _logger.debug(
                    "Using %d RD bin size, %d bins for sex chromosome RD - GC distributions." % (
                        bin_size_sex, n_bins_sex))
                dist_p_sex = np.zeros(n_bins_sex)
                dist_u_sex = np.zeros(n_bins_sex)
                dist_p_gc_sex = np.zeros((n_bins_sex, 101))

            if mt:
                max_bin_mt = int(
                    max(map(lambda x: 5 * x[1] + 5 * x[2], filter(lambda x: Genome.is_mt_chrom(x[0]), his_stat))))
                _logger.debug("Max RD for mitochondria histogram calculated: %d." % max_bin_mt)
                bin_size_mt = max_bin_mt // 1000
                if bin_size_mt == 0:
                    bin_size_mt = 1
                bins_mt = range(0, max_bin_mt // bin_size_mt * bin_size_mt + bin_size_mt, bin_size_mt)
                n_bins_mt = len(bins_mt) - 1
                _logger.debug("Using %d bin size, %d bins for mitochondria chromosome." % (bin_size_mt, n_bins_mt))
                dist_p_mt = np.zeros(n_bins_mt)
                dist_u_mt = np.zeros(n_bins_mt)
                dist_p_gc_mt = np.zeros((n_bins_mt, 101))

            _logger.info("Calculating global statistics.")
            for c in self.io.rd_chromosomes():
                if c in rd_gc_chromosomes:
                    _logger.debug("Chromosome '%s'." % c)
                    his_p = self.io.get_signal(c, bin_size, "RD")
                    his_u = self.io.get_signal(c, bin_size, "RD unique")
                    if Genome.is_autosome(c):
                        dist_p, bins = np.histogram(his_p, bins=bins_auto)
                        dist_u, bins = np.histogram(his_u, bins=bins_auto)
                        gcat = self.io_gc.get_signal(rd_gc_chromosomes[c], None, "GC/AT")
                        dist_p_gc, xbins, ybins = np.histogram2d(his_p, gcp_decompress(gcat, bin_ratio),
                                                                 bins=(bins_auto, range(102)))
                        dist_p_auto += dist_p
                        dist_u_auto += dist_u
                        dist_p_gc_auto += dist_p_gc
                    elif Genome.is_sex_chrom(c):
                        dist_p, bins = np.histogram(his_p, bins=bins_sex)
                        dist_u, bins = np.histogram(his_u, bins=bins_sex)
                        gcat = self.io_gc.get_signal(rd_gc_chromosomes[c], None, "GC/AT")
                        dist_p_gc, xbins, ybins = np.histogram2d(his_p, gcp_decompress(gcat, bin_ratio),
                                                                 bins=(bins_sex, range(102)))
                        dist_p_sex += dist_p
                        dist_u_sex += dist_u
                        dist_p_gc_sex += dist_p_gc
                    elif Genome.is_mt_chrom(c):
                        dist_p, bins = np.histogram(his_p, bins=bins_mt)
                        dist_u, bins = np.histogram(his_u, bins=bins_mt)
                        gcat = self.io_gc.get_signal(rd_gc_chromosomes[c], None, "GC/AT")
                        dist_p_gc, xbins, ybins = np.histogram2d(his_p, gcp_decompress(gcat, bin_ratio),
                                                                 bins=(bins_mt, range(102)))
                        dist_p_mt += dist_p
                        dist_u_mt += dist_u
                        dist_p_gc_mt += dist_p_gc

            if auto:
                n_auto, m_auto, s_auto = fit_normal(np.array(bins_auto[1:-1]), dist_p_auto[1:])[0]
                _logger.info("Autosomes stat - RD parity distribution gaussian fit:  %.2f +- %.2f" % (m_auto, s_auto))
                stat_auto = np.array([max_bin_auto, bin_size_auto, n_bins_auto, n_auto, m_auto, s_auto])
                self.io.create_signal(None, bin_size, "RD p dist", dist_p_auto, flags=FLAG_AUTO)
                self.io.create_signal(None, bin_size, "RD u dist", dist_u_auto, flags=FLAG_AUTO)
                self.io.create_signal(None, bin_size, "RD GC dist", dist_p_gc_auto, flags=FLAG_AUTO)
                self.io.create_signal(None, bin_size, "RD stat", stat_auto, flags=FLAG_AUTO)
                gc_corr_auto = calculate_gc_correction(dist_p_gc_auto, m_auto, s_auto, bin_size_auto)
                self.io.create_signal(None, bin_size, "GC corr", gc_corr_auto, flags=FLAG_AUTO)

            if sex:
                n_sex, m_sex, s_sex = fit_normal(np.array(bins_sex[1:-1]), dist_p_sex[1:])[0]
                _logger.info(
                    "Sex chromosomes stat - RD parity distribution gaussian fit:  %.2f +- %.2f" % (m_sex, s_sex))
                stat_sex = np.array([max_bin_sex, bin_size_sex, n_bins_sex, n_sex, m_sex, s_sex])
                self.io.create_signal(None, bin_size, "RD p dist", dist_p_sex, flags=FLAG_SEX)
                self.io.create_signal(None, bin_size, "RD u dist", dist_u_sex, flags=FLAG_SEX)
                self.io.create_signal(None, bin_size, "RD GC dist", dist_p_gc_sex, flags=FLAG_SEX)
                self.io.create_signal(None, bin_size, "RD stat", stat_sex, flags=FLAG_SEX)
                gc_corr_sex = calculate_gc_correction(dist_p_gc_sex, m_sex, s_sex, bin_size_sex)
                self.io.create_signal(None, bin_size, "GC corr", gc_corr_sex, flags=FLAG_SEX)

            if mt:
                n_mt, m_mt, s_mt = fit_normal(np.array(bins_mt[1:-1]), dist_p_mt[1:])[0]
                _logger.info("Mitochondria stat - RD parity distribution gaussian fit:  %.2f +- %.2f" % (m_mt, s_mt))
                if auto:
                    _logger.info("Mitochondria stat - number of mitochondria per cell:  %.2f +- %.2f" % (
                        2. * m_mt / m_auto, 2. * s_mt / m_auto + s_auto * m_mt / (m_auto * m_auto)))
                stat_mt = np.array([max_bin_mt, bin_size_mt, n_bins_mt, n_mt, m_mt, s_mt])
                self.io.create_signal(None, bin_size, "RD p dist", dist_p_mt, flags=FLAG_MT)
                self.io.create_signal(None, bin_size, "RD u dist", dist_u_mt, flags=FLAG_MT)
                self.io.create_signal(None, bin_size, "RD GC dist", dist_p_gc_mt, flags=FLAG_MT)
                self.io.create_signal(None, bin_size, "RD stat", stat_mt, flags=FLAG_MT)
                gc_corr_mt = calculate_gc_correction(dist_p_gc_mt, m_mt, s_mt, bin_size_mt)
                self.io.create_signal(None, bin_size, "GC corr", gc_corr_mt, flags=FLAG_MT)

            for c in self.io.rd_chromosomes():
                if c in rd_gc_chromosomes:
                    _logger.info(
                        "Calculating GC corrected RD histogram using bin size %d for chromosome '%s'." % (bin_size, c))
                    flag = FLAG_MT if Genome.is_mt_chrom(c) else FLAG_SEX if Genome.is_sex_chrom(c) else FLAG_AUTO
                    his_p = self.io.get_signal(c, bin_size, "RD")
                    _logger.debug("Calculating GC corrected RD")
                    gc_corr = self.io.get_signal(None, bin_size, "GC corr", flag)
                    gcat = self.io_gc.get_signal(rd_gc_chromosomes[c], None, "GC/AT")
                    his_p_corr = his_p / np.array(list(map(lambda x: gc_corr[int(x)], gcp_decompress(gcat, bin_ratio))))

                    self.io.create_signal(c, bin_size, "RD", his_p_corr, flags=FLAG_GC_CORR)

            for c in self.io.rd_chromosomes():
                if (c in rd_gc_chromosomes) and (c in rd_mask_chromosomes):
                    _logger.info("Calculating P-mask histograms using bin size %d for chromosome '%s'." % (bin_size, c))
                    flag = FLAG_MT if Genome.is_mt_chrom(c) else FLAG_SEX if Genome.is_sex_chrom(c) else FLAG_AUTO
                    stat = self.io.get_signal(None, 100, "RD stat", flag)
                    rd_p, rd_u = self.io.read_rd(c)
                    mask = mask_decompress(self.io_mask.get_signal(rd_mask_chromosomes[c], None, "mask"))
                    bin_ratio = bin_size // 100
                    n_bins = len(rd_p) // bin_ratio + 1
                    his_p = np.zeros(n_bins)
                    his_p_corr = np.zeros(n_bins)
                    his_u = np.zeros(n_bins)
                    his_count = np.zeros(n_bins)
                    for (b, e) in mask:
                        for p in range((b - 1) // 100 + 2, (e - 1) // 100):
                            his_p[p // bin_ratio] += rd_p[p]
                            his_u[p // bin_ratio] += rd_u[p]
                            his_count[p // bin_ratio] += 1
                    np.seterr(divide='ignore', invalid='ignore')
                    his_p = his_p / his_count * bin_ratio
                    # his_p[np.isnan(his_p)] = 0.0
                    his_u = his_u / his_count * bin_ratio
                    # his_u[np.isnan(his_u)] = 0.0
                    gc_corr = self.io.get_signal(None, bin_size, "GC corr", flag)
                    gcat = self.io_gc.get_signal(rd_gc_chromosomes[c], None, "GC/AT")
                    his_p_corr = his_p / np.array(list(map(lambda x: gc_corr[int(x)], gcp_decompress(gcat, bin_ratio))))
                    self.io.create_signal(c, bin_size, "RD", his_p, flags=FLAG_USEMASK)
                    self.io.create_signal(c, bin_size, "RD unique", his_u, flags=FLAG_USEMASK)
                    self.io.create_signal(c, bin_size, "RD", his_p_corr, flags=FLAG_GC_CORR | FLAG_USEMASK)

    def ls(self):
        self.io.ls()
