# billing/logic/process/utils/arthrogram.py

from typing import Dict, Optional
from .db_utils import get_order_details, update_bill_status

def check_arthrogram(bill_id: str, order_id: str) -> bool:
    """
    Check if an order is for an arthrogram and update bill status if so.
    
    Args:
        bill_id (str): The provider bill ID
        order_id (str): The order ID to check
        
    Returns:
        bool: True if the order is an arthrogram, False otherwise
    """
    order = get_order_details(order_id)
    
    # Check if bundle_type is arthrogram (case insensitive)
    bundle_type = order.get('bundle_type', '').lower()
    is_arthrogram = bundle_type == 'arthrogram'
    
    if is_arthrogram:
        # Update bill status
        update_bill_status(
            bill_id=bill_id,
            status='ARTHROGRAM',
            action='to_arthrogram',
            error=None
        )
        
    return is_arthrogram