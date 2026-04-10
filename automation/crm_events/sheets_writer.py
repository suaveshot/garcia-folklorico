"""
Google Sheets write helpers for CRM event processing.
Provides append_row, find_row, and update_cell operations
on the Garcia Folklorico CRM spreadsheet.
"""

import logging
import time

log = logging.getLogger(__name__)


def get_spreadsheet(gc, sheet_id):
    """Open the CRM spreadsheet by ID."""
    return gc.open_by_key(sheet_id)


def append_row(ws, row_data, value_input_option="RAW"):
    """Append a row to the bottom of a worksheet's data."""
    ws.append_row(row_data, value_input_option=value_input_option)
    time.sleep(1.5)


def find_row_by_value(ws, col_index, value, start_row=2):
    """Find the first row where column col_index matches value.

    Args:
        ws: Worksheet object
        col_index: 1-based column index to search
        value: Value to match (string comparison)
        start_row: Row to start searching from (skip header)

    Returns:
        Row number (1-based) or None if not found
    """
    col_values = ws.col_values(col_index)
    search_value = str(value)
    for i, cell_value in enumerate(col_values):
        row_num = i + 1
        if row_num < start_row:
            continue
        if str(cell_value) == search_value:
            return row_num
    return None


def update_cell(ws, row, col, value, value_input_option="RAW"):
    """Update a single cell by row and column number (1-based)."""
    ws.update_cell(row, col, value)
    time.sleep(1.0)


def update_row_cells(ws, row, updates, value_input_option="RAW"):
    """Update multiple cells in a row.

    Args:
        ws: Worksheet object
        row: Row number (1-based)
        updates: dict of {col_number: value} (1-based columns)
    """
    for col, value in updates.items():
        ws.update_cell(row, col, value)
    time.sleep(1.5)
