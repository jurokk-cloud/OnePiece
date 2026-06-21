"""Session-state keys shared across OnePiece Studio UI modules.

Streamlit widget keys and ``st.session_state`` entries share one global,
stringly-typed namespace. Every key that is read or written by more than
one function belongs here as a constant, so the cross-module state
contract is visible in one place. Keys used by a single widget in a
single function may stay inline.
"""

from __future__ import annotations

# Workflow builder
WORKFLOW_OPERATIONS = "onepiece_studio_workflow_operations"

# Controlroom filters
CONTROL_STATUS = "onepiece_studio_control_status"
CONTROL_USE_STATUS = "onepiece_studio_control_use_status"
CONTROL_VISIBLE_STATES = "onepiece_studio_control_visible_states"
CONTROL_TEXT_INCLUDE = "onepiece_studio_control_text_include"
CONTROL_TEXT_EXCLUDE = "onepiece_studio_control_text_exclude"
CONTROL_SELECTED_FACETS = "onepiece_studio_control_selected_facets"
CONTROL_NUMERIC = "onepiece_studio_control_numeric"
CONTROL_FMAX_MAX = "onepiece_studio_control_fmax_max"
CONTROL_DROP_CONVERGENCE = "onepiece_studio_control_drop_convergence"
CONTROL_DROP_TEST = "onepiece_studio_control_drop_test"
CONTROL_ROW_KEY = "onepiece_studio_control_row_key"
CONTROL_MATERIAL_QUERY = "onepiece_studio_control_material_query"
CONTROLROOM_ACTIVE_DATAFRAME = "onepiece_studio_controlroom_active_dataframe"

# Welcome / launcher
WELCOME_SELECTION = "onepiece_studio_welcome_selection"

# Cross-cutting session data
SAVED_VIEWS = "onepiece_studio_saved_views"
AUDIT_LOG = "onepiece_studio_audit_log"
PAGE_SIZE = "onepiece_studio_page_size"
CRAWL_OUTPUT_HDF = "onepiece_studio_crawl_output_hdf"
