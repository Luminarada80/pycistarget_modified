from ctxcore.genesig import GeneSignature
from ctxcore.recovery import recovery, aucs as calc_aucs
from ctxcore.recovery import leading_edge4row
from ctxcore.rnkdb import FeatherRankingDatabase
from itertools import repeat
from functools import partial
import logging
import os
import numpy as np
import pandas as pd
import pyranges as pr
import sys
import matplotlib.pyplot as plt
from typing import Union, Dict, Optional, Tuple, Literal
from pycistarget.utils import (
    target_to_query,
    region_sets_to_signature,
    coord_to_region_names)
from pycistarget.motif_enrichment_result import MotifEnrichmentResult

class cisTargetDatabase: 
    """
    cisTarget Database class.
    :class:`cisTargetDatabase` contains a dataframe with motifs as rows, regions as columns and rank as
    values. In addition, is contains a slot to map query regions to regions in the database. For more
    information on how to generate databases, please visit: https://github.com/aertslab/create_cisTarget_databases
    
    Attributes
    ---------
    regions_to_db: pd.DataFrame
        A dataframe containing the mapping between query regions and regions in the database.
    db_rankings: pd.DataFrame
        A dataframe with motifs as rows, regions as columns and rank as values.
    total_regions: int
        Total number of regions in the database
    """
    def __init__(self, 
                fname: str,
                region_sets: Union[Dict[str, pr.PyRanges], pr.PyRanges] = None,
                name: Optional[str] = None,
                fraction_overlap: float = 0.4):
        """
        Initialize cisTargetDatabase
        
        Parameters
        ---------
        fname: str
            Path to feather file containing the cisTarget database (regions_vs_motifs)
        region_sets: Dict or pr.PyRanges, optional
            Dictionary or pr.PyRanges that are going to be analyzed with cistarget. Default: None.
        name: str, optional
            Name for the cistarget database. Default: None
        fraction_overlap: float, optional
            Minimal overlap between query and regions in the database for the mapping.     
        """
        self.regions_to_db, self.db_rankings, self.total_regions = self.load_db(fname,
                                                          region_sets,
                                                          name,
                                                          fraction_overlap)
    def load_db(
        self,        
        fname: str,
        region_sets: Union[Dict[str, pr.PyRanges], pr.PyRanges] = None,
        name: Optional[str] = None,
        fraction_overlap: float = 0.4
        ) -> Tuple[Union[Dict[str, pd.DataFrame], pd.DataFrame, None], pd.DataFrame, int]:
            """
            Load cisTargetDatabase
            
            Parameters
            ---------
            fname: str
                Path to feather file containing the cisTarget database (regions_vs_motifs)
            region_sets: Dict or pr.PyRanges, optional
                Dictionary or pr.PyRanges that are going to be analyzed with cistarget. Default: None.
            name: str, optional
                Name for the cistarget database. Default: None
            fraction_overlap: float, optional
                Minimal overlap between query and regions in the database for the mapping.     
                
            Return
            ---------
            target_to_db_dict: pd.DataFrame
                A dataframe containing the mapping between query regions and regions in the database.
            db_rankings: pd.DataFrame
                A dataframe with motifs as rows, regions as columns and rank as values.
            total_regions: int
                Total number of regions in the database
            """
            #Create logger
            level    = logging.INFO
            format   = '%(asctime)s %(name)-12s %(levelname)-8s %(message)s'
            handlers = [logging.StreamHandler(stream=sys.stdout)]
            logging.basicConfig(level = level, format = format, handlers = handlers)
            log = logging.getLogger('cisTarget')
            
            if name is None:
                name = os.path.basename(fname)
                
            log.info(f'Loading cisTarget database')
            
            db = FeatherRankingDatabase(fname, name=name)
            total_regions = db.total_genes
            db_regions = db.genes
            
            log.info(f'\tTotal Regions: {total_regions}')
            
            prefix = None
            if '__' in db_regions[0]:
                prefix = db_regions[0].split('__')[0]
                db_regions = [x.split('__')[1] for x in db_regions]
            if region_sets is not None:
                if type(region_sets) == dict:
                    target_to_db_dict = {x: target_to_query(region_sets[x], list(db_regions), fraction_overlap = fraction_overlap) for x in region_sets.keys()}
                    target_regions_in_db = list(set(sum([target_to_db_dict[x]['Query'].tolist() for x in target_to_db_dict.keys()],[])))
                elif type(region_sets) == pr.PyRanges:
                    target_to_db = target_to_query(region_sets, list(db_regions), fraction_overlap = fraction_overlap)
                    target_to_db.index = target_to_db['Target']
                    target_to_db_dict = target_to_db #for return purposes
                    target_regions_in_db = list(set(target_to_db['Query'].tolist()))
                else:
                    raise ValueError('region_sets should be either a dict of PyRanges objects or a single PyRanges object, not {}'.format(type(region_sets)))
                name='test'
                if prefix is not None:
                    target_regions_in_db = [prefix + '__' + x for x in target_regions_in_db]
                target_regions_in_db = GeneSignature(name=name, gene2weight=target_regions_in_db)
                db_rankings = db.load(target_regions_in_db)
                if prefix is not None:
                    db_rankings.columns = [x.split('__')[1] for x in db_rankings.columns]
            else:
                log.warn('Loading complete cistarget database, this can take a long time and consumes a lot of memory!')
                target_to_db_dict = None
                db_rankings = db.load_full()
            return target_to_db_dict, db_rankings, total_regions


# cisTarget class
class cisTarget(MotifEnrichmentResult):
    """
    cisTarget class.
    :class:`cisTarget` contains method for motif enrichment analysis on sets of regions. 
    
    Attributes
    ---------
    regions_to_db: pd.DataFrame
        A dataframe containing the mapping between query regions and regions in the database.
    region_set: pr.PyRanges
        A PyRanges containing region coordinates for the regions to be analyzed.
    name: str
        Analysis name
    species: str
        Species from which genomic coordinates come from
    auc_threshold: float, optional
        The fraction of the ranked genome to take into account for the calculation of the
        Area Under the recovery Curve. Default: 0.005
    nes_threshold: float, optional
        The Normalized Enrichment Score (NES) threshold to select enriched features. Default: 3.0
    rank_threshold: float, optional
        The total number of ranked genes to take into account when creating a recovery curve.
        Default: 0.05
    path_to_motif_annotations: str, optional
        Path to motif annotations. If not provided, they will be downloaded from 
        https://resources.aertslab.org based on the species name provided (only possible for mus_musculus,
        homo_sapiens and drosophila_melanogaster). Default: None
    annotation_version: str, optional
        Motif collection version. Default: v9
    annotation: List, optional
        Annotation to use for forming cistromes. It can be 'Direct_annot' (direct evidence that the motif is 
        linked to that TF), 'Motif_similarity_annot' (based on tomtom motif similarity), 'Orthology_annot'
        (based on orthology with a TF that is directly linked to that motif) or 'Motif_similarity_and_Orthology_annot'.
        Default: ['Direct_annot', 'Motif_similarity_annot', 'Orthology_annot', 'Motif_similarity_and_Orthology_annot']
    motif_similarity_fdr: float, optional
        Minimal motif similarity value to consider two motifs similar. Default: 0.001
    orthologous_identity_threshold: float, optional
        Minimal orthology value for considering two TFs orthologous. Default: 0.0
    motifs_to_use: List, optional
        A subset of motifs to use for the analysis. Default: None (All)
    motif_enrichment: pd.DataFrame
        A dataframe containing motif enrichment results
    motif_hits: Dict
        A dictionary containing regions that are considered enriched for each motif.
    cistromes: Dict
        A dictionary containing TF cistromes. Cistromes with no extension contain regions linked to directly
        annotated motifs, while '_extended' cistromes can contain regions linked to motifs annotated by 
        similarity or orthology.
        
    References
    ---------
    Van de Sande B., Flerin C., et al. A scalable SCENIC workflow for single-cell gene regulatory network analysis.
    Nat Protoc. June 2020:1-30. doi:10.1038/s41596-020-0336-2
    """
    def __init__(self, 
                 region_set: pr.PyRanges,
                 name: str,
                 species: Literal[
                    "homo_sapiens", "mus_musculus", "drosophila_melanogaster"],
                 auc_threshold: float = 0.005,
                 nes_threshold: float = 3.0,
                 rank_threshold: float = 0.05,
                 path_to_motif_annotations: Optional[str] = None,
                 annotation_version: str = 'v10',
                 annotation_to_use: list = ['Direct_annot', 'Motif_similarity_annot', 'Orthology_annot', 'Motif_similarity_and_Orthology_annot'],
                 motif_similarity_fdr: float = 0.001,
                 orthologous_identity_threshold: float = 0.0,
                 motifs_to_use: Optional[list] = None):
        """
        Initialize cisTarget class.

        Parameters
        ---------
        ctx_db: :class:`cisTargetDatabase`
            A cistarget database object.
        region_set: pr.PyRanges
            A PyRanges containing region coordinates for the regions to be analyzed.
        name: str
            Analysis name
        species: str
            Species from which genomic coordinates come from
        auc_threshold: float, optional
            The fraction of the ranked genome to take into account for the calculation of the
            Area Under the recovery Curve. Default: 0.005
        nes_threshold: float, optional
            The Normalized Enrichment Score (NES) threshold to select enriched features. Default: 3.0
        rank_threshold: float, optional
            The total number of ranked genes to take into account when creating a recovery curve.
            Default: 0.05
        path_to_motif_annotations: str, optional
            Path to motif annotations. If not provided, they will be downloaded from 
            https://resources.aertslab.org based on the specie name provided (only possible for mus_musculus,
            homo_sapiens and drosophila_melanogaster). Default: None
        annotation_version: str, optional
            Motif collection version. Default: v9
        annotation: List, optional
            Annotation to use for forming cistromes. It can be 'Direct_annot' (direct evidence that the motif is 
            linked to that TF), 'Motif_similarity_annot' (based on tomtom motif similarity), 'Orthology_annot'
            (based on orthology with a TF that is directly linked to that motif) or 'Motif_similarity_and_Orthology_annot'.
            Default: ['Direct_annot', 'Motif_similarity_annot', 'Orthology_annot', 'Motif_similarity_and_Orthology_annot']
        motif_similarity_fdr: float, optional
            Minimal motif similarity value to consider two motifs similar. Default: 0.001
        orthologous_identity_threshold: float, optional
            Minimal orthology value for considering two TFs orthologous. Default: 0.0
        motifs_to_use: List, optional
            A subset of motifs to use for the analysis. Default: None (All)
    
        References
        ---------
        Van de Sande B., Flerin C., et al. A scalable SCENIC workflow for single-cell gene regulatory network analysis.
        Nat Protoc. June 2020:1-30. doi:10.1038/s41596-020-0336-2
        """
        self.region_set = region_set
        self.auc_threshold = auc_threshold
        self.nes_threshold = nes_threshold
        self.rank_threshold = rank_threshold
        super().__init__(
            name=name,
            species = species,
            path_to_motif_annotations = path_to_motif_annotations,
            annotation_version = annotation_version,
            annotation_to_use = annotation_to_use,
            motif_similarity_fdr = motif_similarity_fdr,
            orthologous_identity_threshold = orthologous_identity_threshold,
            motifs_to_use = motifs_to_use
        )
        
    def run_ctx(self,
            ctx_db: cisTargetDatabase):
        """
        Run cisTarget

        Parameters
        ---------
        ctx_db: :class:`cisTargetDatabase`
            A cistarget database object.
    
        References
        ---------
        Van de Sande B., Flerin C., et al. A scalable SCENIC workflow for single-cell gene regulatory network analysis.
        Nat Protoc. June 2020:1-30. doi:10.1038/s41596-020-0336-2
        """
        
        # Create logger
        level    = logging.INFO
        format   = '%(asctime)s %(name)-12s %(levelname)-8s %(message)s'
        handlers = [logging.StreamHandler(stream=sys.stdout)]
        logging.basicConfig(level = level, format = format, handlers = handlers)
        log = logging.getLogger('cisTarget')

        #Hardcoded values
        COLUMN_NAME_NES = "NES"
        COLUMN_NAME_AUC = "AUC"
        COLUMN_NAME_GRP = "GROUP"
        COLUMN_NAME_MOTIF_ID = "MotifID"
        COLUMN_NAME_TARGET_GENES = "TargetRegions"
        COLUMN_NAME_RANK_AT_MAX = "RankAtMax"

        self.regions_to_db = ctx_db.regions_to_db[self.name] if type(ctx_db.regions_to_db) == dict \
            else ctx_db.regions_to_db.loc[
                list(set(coord_to_region_names(self.region_set)) & set(ctx_db.regions_to_db['Target']))]

        # Log
        log.info("Running cisTarget for {} which has {} regions".format(self.name, len(self.regions_to_db['Query'].tolist())))
        # Load signature as Regulon
        region_set_signature = region_sets_to_signature(self.regions_to_db['Query'].tolist(), region_set_name = self.name)
        # Get regions
        regions = np.array(list(region_set_signature.genes))
        # log.info(f'\tregions: {regions[0:5]}')
        
        #subset rankings database on motifs and regions
        if self.motifs_to_use is not None:
            log.info('Using only user provided motifs')
            motifs_not_in_db = set.difference(set(self.motifs_to_use), set(ctx_db.db_rankings.index.values))
            if len(motifs_not_in_db) > 0:
                log.info('Some motifs provided by the parameter <motifs_to_use> are not in the rankings database: {}'.format(motifs_not_in_db))
            motifs_to_use = set(self.motifs_to_use) & set(ctx_db.db_rankings.index.values)
            db_rankings_regions = ctx_db.db_rankings.loc[motifs_to_use, regions]
        else:
            db_rankings_regions = ctx_db.db_rankings[regions]

        #Get features, rankings and weights
        features, rankings = db_rankings_regions.index.values, db_rankings_regions.values
        weights = np.asarray(np.ones(len(regions)))

        # Calculate recovery curves, AUC and NES values.
        aucs = calc_aucs(db_rankings_regions, ctx_db.total_regions, weights, self.auc_threshold)
        ness = (aucs - aucs.mean()) / aucs.std()
        
        # Keep only features that are enriched, i.e. NES sufficiently high.
        enriched_features_idx = ness >= self.nes_threshold
        
        #terminate if no features are enriched
        if sum(enriched_features_idx) == 0:
            log.info("No enriched motifs found for {}".format(self.name))
            self.motif_enrichment = pd.DataFrame(
                data = {
                    'Logo': [], 
                    'Region_set': [], 
                    'Direct_annot': [], 
                    'Motif_similarity_annot': [], 
                    'Orthology_annot': [], 
                    'Motif_similarity_and_Orthology_annot': [], 
                    'NES': [], 
                    'AUC': [],
                    'Rank_at_max': []})
            self.motif_hits: dict = {'Database': {}, 'Region_set': {}}
            self.cistromes: dict = {'Database': {}, 'Region_set': {}}
            return
        
        # Make dataframe
        enriched_features = pd.DataFrame(index=pd.Index(features[enriched_features_idx], name = COLUMN_NAME_MOTIF_ID),
                                    data={COLUMN_NAME_NES: ness[enriched_features_idx],
                                        COLUMN_NAME_AUC: aucs[enriched_features_idx],
                                        COLUMN_NAME_GRP: repeat(region_set_signature.transcription_factor, sum(enriched_features_idx))})
        
        log.info(f'\tMean NES: {enriched_features["NES"].mean():.2f}, std: {enriched_features["NES"].std():.2f}, threshold: {self.nes_threshold} ({len(enriched_features["NES"])}/{len(features)} features enriched)')
        log.info(f'\tMean AUC: {enriched_features["AUC"].mean():.2f}, std: {enriched_features["AUC"].std():.2f}, threshold: {self.auc_threshold} ({len(enriched_features["AUC"])}/{len(features)} features enriched)')
        
        # # Function to write array to a file
        # def append_or_create_file(file_path, data_array):
        #     mode = "a" if os.path.exists(file_path) else "w"
        #     with open(file_path, mode) as file:
        #         file.write(",".join(map(str, data_array)) + "\n")

        # # File paths
        # NES_path = "/gpfs/Labs/Uzun/SCRIPTS/PROJECTS/2024.GRN_BENCHMARKING.MOELLER/SCENIC_PLUS/debugging/NES.csv"
        # AUC_path = "/gpfs/Labs/Uzun/SCRIPTS/PROJECTS/2024.GRN_BENCHMARKING.MOELLER/SCENIC_PLUS/debugging/AUC.csv"

        # # Write data
        # append_or_create_file(NES_path, enriched_features["NES"])
        # append_or_create_file(AUC_path, enriched_features["AUC"])
        
        # Recovery analysis
        rccs, _ = recovery(db_rankings_regions, ctx_db.total_regions, weights, int(self.rank_threshold*ctx_db.total_regions), self.auc_threshold, no_auc=True)  
        avgrcc = rccs.mean(axis=0)        
        avg2stdrcc = avgrcc + 2.0 * rccs.std(axis=0)
        # Select features
        rccs = rccs[enriched_features_idx, :]
        rankings = rankings[enriched_features_idx, :]
        # Format df
        enriched_features.columns = pd.MultiIndex.from_tuples(list(zip(repeat("Enrichment"),
                                                                        enriched_features.columns)))
        df_rnks = pd.DataFrame(index=enriched_features.index,
                            columns=pd.MultiIndex.from_tuples(list(zip(repeat("Ranking"), regions))),
                            data=rankings)
        df_rccs = pd.DataFrame(index=enriched_features.index,
                            columns=pd.MultiIndex.from_tuples(list(zip(repeat("Recovery"), np.arange(int(self.rank_threshold*ctx_db.total_regions))))),
                            data=rccs)
        enriched_features = pd.concat([enriched_features, df_rccs, df_rnks], axis=1)
        # Calculate the leading edges for each row. Always return importance from gene inference phase.
        weights = np.asarray([region_set_signature[region] for region in regions])
        enriched_features[[("Enrichment", COLUMN_NAME_TARGET_GENES), ("Enrichment", COLUMN_NAME_RANK_AT_MAX)]] = enriched_features.apply(
            partial(leading_edge4row, avg2stdrcc=avg2stdrcc, genes=regions, weights=weights), axis=1)
        enriched_features = enriched_features['Enrichment'].rename_axis(None)
        # Format enriched features
        enriched_features.columns = ['NES', 'AUC', 'Region_set', 'Motif_hits', 'Rank_at_max']
        enriched_features = enriched_features.sort_values('NES', ascending=False)
        self.motif_enrichment = enriched_features[['Region_set', 'NES', 'AUC', 'Rank_at_max']]
        # print(f'\tself.motif_enrichment = {enriched_features.head()}')
        
        # Annotation
        log.info("\tAnnotating motifs")
        self.add_motif_annotation()
        log.info(f"\t\tDone annotating motifs")
        
        # Motif hits
        log.info("\tFinding motif hits for " + self.name)
        db_motif_hits = {key: [enriched_features.loc[key, 'Motif_hits'][i][0] for i in range(len(enriched_features.loc[key, 'Motif_hits']))] for key in enriched_features.index}
        rs_motif_hits = {key: list(set(self.regions_to_db.loc[self.regions_to_db['Query'].isin(db_motif_hits[key]), 'Target'].tolist())) for key in db_motif_hits.keys()}
        self.motif_hits = {'Database': db_motif_hits, 'Region_set': rs_motif_hits}
        self.motif_enrichment['Motif_hits'] = [len(db_motif_hits[i]) for i in db_motif_hits.keys()]
        log.info(f'\t\tNumber of motif hits: {len(self.motif_enrichment["Motif_hits"])}')
        # log.info(f'motif_enrichment["Motif_hits"] = {self.motif_enrichment["Motif_hits"][0:5]}')
        
        # Cistromes
        log.info("\tGetting cistromes for " + self.name)
        self.get_cistromes()
        log.info("\t\tDone getting cistromes\n")
