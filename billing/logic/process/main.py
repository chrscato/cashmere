# billing/logic/process/main.py

import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

# Configure path
project_root = Path(__file__).resolve().parents[2]
sys.path.append(str(project_root))

# Import utilities
from .utils.loader import load_mapped_bills, load_bill_data
from .utils.validation import validate_provider_info, compare_cpt_codes
from .utils.db_utils import update_bill_status, update_line_item
from .utils.arthrogram import check_arthrogram

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(project_root / 'logs' / f'process_{datetime.now().strftime("%Y%m%d")}.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def process_provider_validation(bill_id: str, bill: Dict, provider: Optional[Dict]) -> bool:
    """
    Check if provider information is complete enough to proceed to next validation step.
    
    Args:
        bill_id: The provider bill ID
        bill: The provider bill record
        provider: The provider record (or None if not found)
        
    Returns:
        bool: True if can proceed to next check, False if needs to stop for missing info
    """
    logger.info(f"Checking provider information completeness for bill {bill_id}")
    
    # If provider record not found, cannot proceed
    if not provider:
        error_msg = "Provider information not found"
        logger.warning(f"Cannot proceed: {error_msg}")
        update_bill_status(bill_id, "FLAGGED", "update_prov_info", error_msg)
        return False
    
    # Check provider information completeness
    validation_results = validate_provider_info(bill, provider)
    
    if validation_results['is_valid']:
        logger.info(f"Provider information complete, proceeding to next check")
        return True
    else:
        # Build error message based on missing fields
        missing_fields = [
            field.replace('_present', '').replace('_', ' ').title()
            for field, is_present in validation_results.items()
            if field != 'is_valid' and not is_present
        ]
            
        error_msg = "Cannot proceed: Missing required provider fields - " + ", ".join(missing_fields)
        logger.warning(error_msg)
        
        # Update bill status to indicate provider info needs to be updated
        update_bill_status(bill_id, "FLAGGED", "update_prov_info", error_msg)
        return False


def process_bill(bill_id: str) -> Dict:
    """
    Process a single bill through all validation steps.
    
    Args:
        bill_id: The provider bill ID
        
    Returns:
        Dict with processing results
    """
    logger.info(f"Processing bill {bill_id}")
    
    try:
        # Step 1: Load all needed data
        bill, bill_items, order, order_items, provider = load_bill_data(bill_id)
        
        if not bill:
            logger.error(f"Bill {bill_id} not found")
            return {"status": "ERROR", "message": "Bill not found"}
            
        if not bill_items:
            logger.error(f"Bill {bill_id} has no line items")
            update_bill_status(bill_id, "FLAGGED", "to_review", "No line items found")
            return {"status": "ERROR", "message": "No line items found"}
            
        if not order:
            logger.error(f"Bill {bill_id} has no associated order")
            update_bill_status(bill_id, "FLAGGED", "to_review", "No associated order found")
            return {"status": "ERROR", "message": "No associated order found"}
        
        # Step 2: Check if this is an arthrogram
        if check_arthrogram(bill_id, order.get('Order_ID', '')):
            logger.info(f"Bill {bill_id} is for an arthrogram, routed to specialist processing")
            return {"status": "ARTHROGRAM", "message": "Routed to arthrogram processing"}
        
        # Step 3: Validate provider information
        if not process_provider_validation(bill_id, bill, provider):
            return {"status": "FLAGGED", "message": "Provider validation failed"}
        
        # Step 4: Validate CPT codes (we'll implement this next)
        # For now, just update the bill status to proceed to the next step
        update_bill_status(bill_id, "VALIDATED", "to_review", None)
        return {"status": "SUCCESS", "message": "Provider validation passed"}
        
    except Exception as e:
        logger.exception(f"Error processing bill {bill_id}: {str(e)}")
        update_bill_status(bill_id, "ERROR", "to_review", f"Processing error: {str(e)}")
        return {"status": "ERROR", "message": str(e)}


def run_processing(limit: Optional[int] = None):
    """
    Run the processing pipeline on all mapped bills.
    
    Args:
        limit: Optional maximum number of bills to process
    """
    logger.info("Starting bill processing")
    
    # Get bills that need processing
    bills = load_mapped_bills(limit)
    logger.info(f"Found {len(bills)} bills to process")
    
    # Process each bill
    results = {
        "total": len(bills),
        "success": 0,
        "flagged": 0,
        "error": 0,
        "arthrogram": 0
    }
    
    for bill in bills:
        bill_id = bill['id']
        result = process_bill(bill_id)
        status = result.get("status", "ERROR")
        
        if status == "SUCCESS":
            results["success"] += 1
        elif status == "FLAGGED":
            results["flagged"] += 1
        elif status == "ARTHROGRAM":
            results["arthrogram"] += 1
        else:
            results["error"] += 1
    
    logger.info(f"Processing complete: {results}")
    return results


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Process provider bills')
    parser.add_argument('--limit', type=int, help='Maximum number of bills to process')
    parser.add_argument('--bill', type=str, help='Process a specific bill ID')
    
    args = parser.parse_args()
    
    if args.bill:
        result = process_bill(args.bill)
        print(f"Result: {result}")
    else:
        results = run_processing(args.limit)
        print(f"Results: {results}")