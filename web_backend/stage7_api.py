"""Stage 7 API mixin: formula handbook, favorites and reviewed file imports."""
from __future__ import annotations
import education_profile
from web_backend.formula_book import list_formulas,formula_detail,facets,set_favorite,create_formula,update_formula
from web_backend.formula_import import MAX_IMPORT_BYTES,create_draft,draft as import_draft,update_item as update_import_item,approve_item,commit as commit_import

def _truth(value