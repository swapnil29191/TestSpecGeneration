"""Multi-source Excel requirement ingestion (DNG exports -> standardized JSON).

Modular pipeline, each stage independently testable:
  excel_reader   -> raw worksheet rows
  column_mapper  -> canonical field names regardless of source column naming
  normalizer     -> standardized requirement objects with traceability
  consolidator   -> merges multiple files/sheets, flags duplicates/broken links
  pipeline       -> orchestrates the stages above for the API layer
"""
