type SourceRow = {
  claim_id?: string
  source_doi?: string
}

export function buildSourceUrl(row: SourceRow): string {
  const claimId = String(row.claim_id || '').trim()
  const sourceDoi = String(row.source_doi || '').trim()
  if (!sourceDoi) return ''

  const lowerSource = sourceDoi.toLowerCase()
  if (lowerSource.startsWith('http://') || lowerSource.startsWith('https://')) {
    return sourceDoi
  }

  if (claimId.toUpperCase().startsWith('PUBMED_') && /^\d+$/.test(sourceDoi)) {
    return `https://pubmed.ncbi.nlm.nih.gov/${sourceDoi}/`
  }
  if (claimId.toUpperCase().startsWith('CTGOV_') && sourceDoi.toUpperCase().startsWith('NCT')) {
    return `https://clinicaltrials.gov/study/${sourceDoi}`
  }
  if (claimId.toUpperCase().startsWith('NCBI_GENE_') && /^\d+$/.test(sourceDoi)) {
    return `https://www.ncbi.nlm.nih.gov/gene/${sourceDoi}`
  }
  if (claimId.toUpperCase().startsWith('UNIPROT_')) {
    return `https://www.uniprot.org/uniprotkb/${sourceDoi}`
  }
  if (claimId.toUpperCase().startsWith('GO_')) {
    return `https://www.ebi.ac.uk/QuickGO/term/${sourceDoi}`
  }
  if (claimId.toUpperCase().startsWith('REACTOME_')) {
    return `https://reactome.org/content/detail/${sourceDoi}`
  }
  if (claimId.toUpperCase().startsWith('GEO_')) {
    return `https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=${sourceDoi}`
  }
  if (claimId.toUpperCase().startsWith('ARRAYEXPRESS_')) {
    return `https://www.ebi.ac.uk/biostudies/arrayexpress/studies/${sourceDoi}`
  }
  if (claimId.toUpperCase().startsWith('KEGG_')) {
    return `https://www.kegg.jp/entry/${sourceDoi}`
  }
  if (claimId.toUpperCase().startsWith('PRIDE_')) {
    return `https://www.ebi.ac.uk/pride/archive/projects/${sourceDoi}`
  }
  if (claimId.toUpperCase().startsWith('METABOLOMICS_WORKBENCH_')) {
    return `https://www.metabolomicsworkbench.org/data/show_study.php?STUDY_ID=${sourceDoi}`
  }
  if (claimId.toUpperCase().startsWith('CHEMBL_')) {
    return `https://www.ebi.ac.uk/chembl/compound_report_card/${sourceDoi}/`
  }
  if (claimId.toUpperCase().startsWith('OPEN_TARGETS_')) {
    return `https://platform.opentargets.org/search?q=${sourceDoi}`
  }
  if (claimId.toUpperCase().startsWith('FDA_LABELS_')) {
    return 'https://open.fda.gov/apis/drug/label/'
  }
  if (/^\d+$/.test(sourceDoi)) {
    return `https://pubmed.ncbi.nlm.nih.gov/${sourceDoi}/`
  }
  if (sourceDoi.toUpperCase().startsWith('NCT')) {
    return `https://clinicaltrials.gov/study/${sourceDoi}`
  }

  return `https://doi.org/${sourceDoi}`
}
