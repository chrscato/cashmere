# billing/logic/process/utils/db_queries.py

import sqlite3
from typing import Dict, List, Tuple, Optional, Any, Set


def get_db_connection(db_path: str = "monolith.db") -> sqlite3.Connection:
    """Get a connection to the SQLite database."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # Return results as dictionaries
    return conn


def get_mapped_bills(limit: Optional[int] = None) -> List[Dict]:
    """Get all provider bills with MAPPED status."""
    conn = get_db_connection()
    query = """
        SELECT * FROM ProviderBill 
        WHERE status = 'MAPPED'
        ORDER BY created_at DESC
    """
    
    if limit:
        query += f" LIMIT {limit}"
    
    cursor = conn.cursor()
    cursor.execute(query)
    bills = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return bills


def get_bill_with_line_items(bill_id: str) -> Tuple[Dict, List[Dict]]:
    """Get a bill with all its line items."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get the bill
    cursor.execute("SELECT * FROM ProviderBill WHERE id = ?", (bill_id,))
    bill = dict(cursor.fetchone())
    
    # Get the bill line items
    cursor.execute("""
        SELECT * FROM BillLineItem 
        WHERE provider_bill_id = ?
        ORDER BY date_of_service
    """, (bill_id,))
    line_items = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    return bill, line_items


def get_order_details(order_id: str) -> Dict:
    """Get all details for a specific order."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT * FROM orders
        WHERE Order_ID = ?
    """, (order_id,))
    order = dict(cursor.fetchone())
    
    conn.close()
    return order


def get_order_line_items(order_id: str) -> List[Dict]:
    """Get all line items for a specific order."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT * FROM order_line_items
        WHERE Order_ID = ?
        ORDER BY line_number
    """, (order_id,))
    line_items = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    return line_items


def get_provider_details(provider_id: str) -> Dict:
    """Get provider details using provider_id."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 
            "Name", "DBA Name Billing Name", "Billing Name", 
            "Address Line 1", "Address Line 2", "City", "State", "Postal Code", 
            "Billing Address 1", "Billing Address 2", "Billing Address City", 
            "Billing Address State", "Billing Address Postal Code", 
            "Phone", "Fax Number", "TIN", "NPI", 
            "Provider Network", "Provider Type", "Provider Status"
        FROM providers
        WHERE PrimaryKey = ?
    """, (provider_id,))
    row = cursor.fetchone()
    provider = dict(row) if row else {}
    
    conn.close()
    return provider


def get_cpt_categories(cpt_codes: List[str]) -> Dict[str, Tuple[str, str]]:
    """
    Get category and subcategory for multiple CPT codes.
    Returns a dictionary mapping CPT codes to (category, subcategory) tuples.
    """
    if not cpt_codes:
        return {}
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create parameter placeholders for SQL query
    placeholders = ', '.join(['?'] * len(cpt_codes))
    
    cursor.execute(f"""
        SELECT proc_cd, category, subcategory
        FROM dim_proc
        WHERE proc_cd IN ({placeholders})
    """, cpt_codes)
    
    results = {}
    for row in cursor.fetchall():
        results[row['proc_cd']] = (row['category'], row['subcategory'])
    
    conn.close()
    return results


def get_in_network_rate(tin: str, cpt_code: str, modifier: Optional[str] = None) -> Optional[float]:
    """Get in-network rate for a specific provider and CPT code."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT rate
        FROM ppo
        WHERE TIN = ? AND proc_cd = ? AND (modifier = ? OR (? IS NULL AND modifier IS NULL))
        LIMIT 1
    """, (tin, cpt_code, modifier, modifier))
    
    row = cursor.fetchone()
    rate = float(row['rate']) if row and row['rate'] else None
    
    conn.close()
    return rate


def get_out_of_network_rate(order_id: str, cpt_code: str, modifier: Optional[str] = None) -> Optional[float]:
    """Get out-of-network rate for a specific order and CPT code."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT rate
        FROM ota
        WHERE ID_Order_PrimaryKey = ? AND CPT = ? AND (modifier = ? OR (? IS NULL AND modifier IS NULL))
        LIMIT 1
    """, (order_id, cpt_code, modifier, modifier))
    
    row = cursor.fetchone()
    rate = float(row['rate']) if row and row['rate'] else None
    
    conn.close()
    return rate


def update_bill_status(bill_id: str, status: str, action: str, error: Optional[str] = None) -> bool:
    """Update the status, action, and error message of a provider bill."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        UPDATE ProviderBill
        SET status = ?, action = ?, last_error = ?
        WHERE id = ?
    """, (status, action, error, bill_id))
    
    conn.commit()
    success = cursor.rowcount > 0
    conn.close()
    return success


def update_line_item(line_id: int, decision: str, allowed_amount: Optional[float] = None, 
                     reason_code: Optional[str] = None) -> bool:
    """Update a bill line item with decision and allowed amount."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        UPDATE BillLineItem
        SET decision = ?, allowed_amount = ?, reason_code = ?
        WHERE id = ?
    """, (decision, allowed_amount, reason_code, line_id))
    
    conn.commit()
    success = cursor.rowcount > 0
    conn.close()
    return success


def compare_cpt_codes(bill_items: List[Dict], order_items: List[Dict]) -> Dict:
    """
    Flexible CPT code comparison between billed and ordered items.
    Handles many-to-many relationships between line items.
    
    Returns:
        Dict containing:
        - exact_matches: CPT codes that match exactly
        - billed_not_ordered: CPT codes billed but not ordered
        - ordered_not_billed: CPT codes ordered but not billed
        - category_matches: CPT codes that match by category but not code
        - category_mismatches: CPT codes with no category match
    """
    # Get unique CPT codes from each source with counts
    billed_cpts = {}
    ordered_cpts = {}
    
    for item in bill_items:
        cpt = item['cpt_code'].strip() if item['cpt_code'] else ""
        if cpt:
            billed_cpts[cpt] = billed_cpts.get(cpt, 0) + 1
            
    for item in order_items:
        cpt = item['CPT'].strip() if item['CPT'] else ""
        if cpt:
            ordered_cpts[cpt] = ordered_cpts.get(cpt, 0) + 1
    
    # Find exact matches and differences
    exact_matches = []
    for cpt in set(billed_cpts.keys()).intersection(set(ordered_cpts.keys())):
        exact_matches.append({
            'cpt': cpt,
            'billed_count': billed_cpts[cpt],
            'ordered_count': ordered_cpts[cpt]
        })
    
    billed_not_ordered = list(set(billed_cpts.keys()) - set(ordered_cpts.keys()))
    ordered_not_billed = list(set(ordered_cpts.keys()) - set(billed_cpts.keys()))
    
    # Get categories for codes that don't match exactly
    unmatched_cpts = billed_not_ordered + ordered_not_billed
    if not unmatched_cpts:
        return {
            'exact_matches': exact_matches,
            'billed_not_ordered': [],
            'ordered_not_billed': [],
            'category_matches': [],
            'category_mismatches': []
        }
    
    # Get category information
    categories = get_cpt_categories(unmatched_cpts)
    
    # Build category mapping
    billed_categories = {}
    ordered_categories = {}
    
    for cpt in billed_not_ordered:
        if cpt in categories:
            cat_key = categories[cpt]
            if cat_key not in billed_categories:
                billed_categories[cat_key] = []
            billed_categories[cat_key].append(cpt)
    
    for cpt in ordered_not_billed:
        if cpt in categories:
            cat_key = categories[cpt]
            if cat_key not in ordered_categories:
                ordered_categories[cat_key] = []
            ordered_categories[cat_key].append(cpt)
    
    # Find category matches
    category_matches = []
    category_mismatches = []
    
    for cat_key, billed_cpts_in_cat in billed_categories.items():
        if cat_key in ordered_categories:
            # We have a category match
            for billed_cpt in billed_cpts_in_cat:
                category_matches.append({
                    'billed_cpt': billed_cpt,
                    'ordered_cpts': ordered_categories[cat_key],
                    'category': cat_key[0],
                    'subcategory': cat_key[1]
                })
        else:
            # No category match
            for billed_cpt in billed_cpts_in_cat:
                category_mismatches.append({
                    'cpt': billed_cpt,
                    'category': cat_key[0],
                    'subcategory': cat_key[1]
                })
    
    return {
        'exact_matches': exact_matches,
        'billed_not_ordered': billed_not_ordered,
        'ordered_not_billed': ordered_not_billed,
        'category_matches': category_matches,
        'category_mismatches': category_mismatches
    }


def get_ancillary_codes() -> Set[str]:
    """Load list of ancillary CPT codes that should be ignored in validation."""
    # Implement loading from ancillary_codes.json or a database table
    # For now, return a small hardcoded set
    return {
        "36415", "36416", "99000", "99001", "A4550", "A4556", 
        "A4558", "A4570", "A4580", "A4590", "Q4001", "T1015"
    }


def validate_provider_info(bill: Dict, provider: Dict) -> Dict[str, bool]:
    """
    Validate provider information between bill and provider records.
    
    Returns:
        Dict with validation results for each field
    """
    results = {}
    
    # Clean TIN (removing any non-digits)
    bill_tin = ''.join(filter(str.isdigit, bill['billing_provider_tin'] or ""))
    provider_tin = ''.join(filter(str.isdigit, provider.get('TIN', "") or ""))
    
    results['tin_match'] = bill_tin == provider_tin and bool(bill_tin)
    results['npi_match'] = bill['billing_provider_npi'] == provider.get('NPI') and bool(bill['billing_provider_npi'])
    
    # Flexible name matching (case insensitive, substring)
    bill_name = (bill['billing_provider_name'] or "").lower()
    provider_names = [
        (provider.get('Name') or "").lower(),
        (provider.get('DBA Name Billing Name') or "").lower(),
        (provider.get('Billing Name') or "").lower()
    ]
    
    results['name_match'] = any(
        (name and bill_name and (name in bill_name or bill_name in name))
        for name in provider_names if name
    )
    
    # Overall validation result
    results['is_valid'] = results['tin_match'] and (results['npi_match'] or results['name_match'])
    
    return results