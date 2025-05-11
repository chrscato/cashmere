# billing/webapp/bill_review/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.db import connection
from django.urls import reverse
from django.http import HttpResponseRedirect
from django.contrib import messages
import logging
from .forms import BillUpdateForm, LineItemUpdateForm
from django.contrib.auth.decorators import login_required

logger = logging.getLogger(__name__)

def get_flagged_bills():
    """Get all flagged bills."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    pb.id,
                    pb.claim_id,
                    pb.patient_name,
                    pb.status,
                    pb.action,
                    pb.last_error,
                    pb.created_at,
                    p."DBA Name Billing Name" as provider_name
                FROM ProviderBill pb
                LEFT JOIN orders o ON pb.claim_id = o.Order_ID
                LEFT JOIN providers p ON o.provider_id = p.PrimaryKey
                WHERE pb.status IN ('FLAGGED', 'REVIEW_FLAG')
                ORDER BY pb.created_at DESC
            """)
            columns = [col[0] for col in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Error retrieving flagged bills: {e}")
        return []

def get_error_bills():
    """Get all error bills."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    pb.id,
                    pb.claim_id,
                    pb.patient_name,
                    pb.status,
                    pb.action,
                    pb.last_error,
                    pb.created_at,
                    p."DBA Name Billing Name" as provider_name
                FROM ProviderBill pb
                LEFT JOIN orders o ON pb.claim_id = o.Order_ID
                LEFT JOIN providers p ON o.provider_id = p.PrimaryKey
                WHERE pb.status = 'ERROR'
                ORDER BY pb.created_at DESC
            """)
            columns = [col[0] for col in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Error retrieving error bills: {e}")
        return []

def get_arthrogram_bills():
    """Get all arthrogram bills."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    pb.id,
                    pb.claim_id,
                    pb.patient_name,
                    pb.status,
                    pb.action,
                    pb.last_error,
                    pb.created_at,
                    p."DBA Name Billing Name" as provider_name
                FROM ProviderBill pb
                LEFT JOIN orders o ON pb.claim_id = o.Order_ID
                LEFT JOIN providers p ON o.provider_id = p.PrimaryKey
                WHERE pb.status = 'ARTHROGRAM'
                ORDER BY pb.created_at DESC
            """)
            columns = [col[0] for col in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Error retrieving arthrogram bills: {e}")
        return []

def get_bill_details(bill_id):
    """Get details for a specific bill."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    pb.*,
                    o.Order_ID,
                    o.bundle_type,
                    o.created_at,
                    o.PatientName,
                    o.Patient_First_Name,
                    o.Patient_Last_Name,
                    o.Patient_DOB,
                    o.Patient_Address,
                    o.Patient_City,
                    o.Patient_State,
                    o.Patient_Zip,
                    o.PatientPhone,
                    o.Order_Type,
                    o.Jurisdiction_State,
                    o.provider_id,
                    o.provider_name,
                    o.BILLS_PAID,
                    o.FULLY_PAID,
                    o.BILLS_REC,
                    p."DBA Name Billing Name" as provider_name,
                    p.TIN,
                    p.NPI,
                    p."Provider Network"
                FROM ProviderBill pb
                LEFT JOIN orders o ON pb.claim_id = o.Order_ID
                LEFT JOIN providers p ON o.provider_id = p.PrimaryKey
                WHERE pb.id = %s
            """, [bill_id])
            columns = [col[0] for col in cursor.description]
            row = cursor.fetchone()
            return dict(zip(columns, row)) if row else None
    except Exception as e:
        logger.error(f"Error retrieving bill details for {bill_id}: {e}")
        return None

def get_bill_line_items(bill_id):
    """Get line items for a specific bill."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    bli.*,
                    oli.CPT as order_cpt,
                    oli.modifier as order_modifier,
                    oli.units as order_units,
                    oli.charge_amount as order_charge,
                    oli.BILL_REVIEWED
                FROM BillLineItem bli
                LEFT JOIN orders o ON bli.provider_bill_id = o.Order_ID
                LEFT JOIN order_line_items oli ON o.Order_ID = oli.Order_ID 
                    AND bli.cpt_code = oli.CPT
                WHERE bli.provider_bill_id = %s
                ORDER BY bli.date_of_service
            """, [bill_id])
            columns = [col[0] for col in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Error retrieving line items for bill {bill_id}: {e}")
        return []

def get_provider_for_bill(bill_id):
    """Get provider information for a bill."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    p.PrimaryKey,
                    p."DBA Name Billing Name",
                    p."Billing Name",
                    p."Address Line 1",
                    p."Address Line 2",
                    p.City,
                    p.State,
                    p."Postal Code",
                    p.TIN,
                    p.NPI,
                    p."Provider Network",
                    p."Provider Type",
                    p."Provider Status",
                    p."Billing Address 1",
                    p."Billing Address 2",
                    p."Billing Address City",
                    p."Billing Address State",
                    p."Billing Address Postal Code",
                    p.Phone,
                    p."Fax Number"
                FROM ProviderBill pb
                JOIN orders o ON pb.claim_id = o.Order_ID
                JOIN providers p ON o.provider_id = p.PrimaryKey
                WHERE pb.id = %s
            """, [bill_id])
            columns = [col[0] for col in cursor.description]
            row = cursor.fetchone()
            return dict(zip(columns, row)) if row else None
    except Exception as e:
        logger.error(f"Error retrieving provider for bill {bill_id}: {e}")
        return None

def update_bill_status(bill_id, status, action, last_error):
    """Update bill status, action, and error message."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                UPDATE ProviderBill
                SET status = %s, action = %s, last_error = %s
                WHERE id = %s
            """, [status, action, last_error, bill_id])
            
            # If status is REVIEWED, update order line items
            if status == 'REVIEWED':
                # Get the claim_id (Order_ID) for this bill
                cursor.execute("""
                    SELECT claim_id FROM ProviderBill WHERE id = %s
                """, [bill_id])
                row = cursor.fetchone()
                if row and row[0]:
                    order_id = row[0]
                    # Get all CPT codes for this bill
                    cursor.execute("""
                        SELECT cpt_code FROM BillLineItem WHERE provider_bill_id = %s
                    """, [bill_id])
                    cpt_codes = [row[0] for row in cursor.fetchall()]
                    # Update order line items as reviewed
                    if cpt_codes:
                        placeholders = ', '.join(['%s'] * len(cpt_codes))
                        cursor.execute(f"""
                            UPDATE order_line_items
                            SET BILL_REVIEWED = %s
                            WHERE Order_ID = %s AND CPT IN ({placeholders})
                        """, [bill_id, order_id] + cpt_codes)
            
            return True
    except Exception as e:
        logger.error(f"Error updating bill status for {bill_id}: {e}")
        return False

def dashboard(request):
    """Display bills by their status category."""
    flagged_bills = get_flagged_bills()
    error_bills = get_error_bills()
    arthrogram_bills = get_arthrogram_bills()
    
    return render(request, 'bill_review/dashboard.html', {
        'flagged_bills': flagged_bills,
        'error_bills': error_bills,
        'arthrogram_bills': arthrogram_bills,
    })

def bill_detail(request, bill_id):
    """Show details for a specific bill and allow updates."""
    bill = get_bill_details(bill_id)
    if not bill:
        messages.error(request, 'Bill not found.')
        return HttpResponseRedirect(reverse('bill_review:dashboard'))
        
    line_items = get_bill_line_items(bill_id)
    provider = get_provider_for_bill(bill_id) if bill.get('claim_id') else None
    
    if request.method == 'POST':
        form = BillUpdateForm(request.POST)
        if form.is_valid():
            status = form.cleaned_data['status']
            action = form.cleaned_data['action']
            last_error = form.cleaned_data['last_error']
            if update_bill_status(bill_id, status, action, last_error):
                messages.success(request, 'Bill updated successfully.')
            else:
                messages.error(request, 'Failed to update bill.')
            return HttpResponseRedirect(reverse('bill_review:bill_detail', args=[bill_id]))
    else:
        form = BillUpdateForm(initial={
            'status': bill.get('status'),
            'action': bill.get('action'),
            'last_error': bill.get('last_error')
        })
    
    return render(request, 'bill_review/bill_detail.html', {
        'bill': bill,
        'line_items': line_items,
        'provider': provider,
        'form': form,
    })

def line_item_update(request, item_id):
    """Update a specific line item."""
    if request.method == 'POST':
        form = LineItemUpdateForm(request.POST)
        if form.is_valid():
            try:
                with connection.cursor() as cursor:
                    # Get the bill_id for redirect
                    cursor.execute("""
                        SELECT provider_bill_id 
                        FROM BillLineItem 
                        WHERE id = %s
                    """, [item_id])
                    row = cursor.fetchone()
                    if not row:
                        messages.error(request, 'Line item not found.')
                        return HttpResponseRedirect(reverse('bill_review:dashboard'))
                    
                    bill_id = row[0]
                    
                    # Update the line item
                    cursor.execute("""
                        UPDATE BillLineItem
                        SET cpt_code = %s,
                            modifier = %s,
                            units = %s,
                            charge_amount = %s,
                            allowed_amount = %s,
                            decision = %s,
                            reason_code = %s
                        WHERE id = %s
                    """, [
                        form.cleaned_data['cpt_code'],
                        form.cleaned_data['modifier'],
                        form.cleaned_data['units'],
                        form.cleaned_data['charge_amount'],
                        form.cleaned_data['allowed_amount'],
                        form.cleaned_data['decision'],
                        form.cleaned_data['reason_code'],
                        item_id
                    ])
                
                messages.success(request, 'Line item updated successfully.')
                return HttpResponseRedirect(reverse('bill_review:bill_detail', args=[bill_id]))
            except Exception as e:
                logger.error(f"Error updating line item {item_id}: {e}")
                messages.error(request, 'Failed to update line item.')
    
    return HttpResponseRedirect(reverse('bill_review:dashboard'))

def reset_bill(request, bill_id):
    """Reset a bill to MAPPED status for reprocessing."""
    if request.method == 'POST':
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    UPDATE ProviderBill
                    SET status = 'MAPPED', action = NULL, last_error = NULL
                    WHERE id = %s
                """, [bill_id])
            messages.success(request, 'Bill has been reset to MAPPED status.')
        except Exception as e:
            logger.error(f"Error resetting bill {bill_id}: {e}")
            messages.error(request, 'Failed to reset bill.')
    
    return HttpResponseRedirect(reverse('bill_review:dashboard'))

@login_required
def update_provider(request, provider_id):
    if request.method == 'POST':
        try:
            with connection.cursor() as cursor:
                # Update provider information
                cursor.execute("""
                    UPDATE providers 
                    SET DBA_Name_Billing_Name = %s,
                        Billing_Name = %s,
                        Address_Line_1 = %s,
                        Address_Line_2 = %s,
                        City = %s,
                        State = %s,
                        Postal_Code = %s,
                        TIN = %s,
                        NPI = %s,
                        Provider_Network = %s
                    WHERE PrimaryKey = %s
                """, [
                    request.POST.get('dba_name'),
                    request.POST.get('billing_name'),
                    request.POST.get('address1'),
                    request.POST.get('address2'),
                    request.POST.get('city'),
                    request.POST.get('state'),
                    request.POST.get('postal_code'),
                    request.POST.get('tin'),
                    request.POST.get('npi'),
                    request.POST.get('network'),
                    provider_id
                ])
                
                messages.success(request, 'Provider information updated successfully.')
        except Exception as e:
            logger.error(f"Error updating provider {provider_id}: {str(e)}")
            messages.error(request, 'Failed to update provider information.')
    
    # Redirect back to the bill detail page
    return redirect('bill_review:bill_detail', bill_id=request.GET.get('bill_id'))

@login_required
def update_bill(request, bill_id):
    """Update bill status and information."""
    if request.method == 'POST':
        form = BillUpdateForm(request.POST)
        if form.is_valid():
            try:
                with connection.cursor() as cursor:
                    cursor.execute("""
                        UPDATE ProviderBill
                        SET status = %s,
                            action = %s,
                            last_error = %s
                        WHERE id = %s
                    """, [
                        form.cleaned_data['status'],
                        form.cleaned_data['action'],
                        form.cleaned_data['last_error'],
                        bill_id
                    ])
                messages.success(request, 'Bill updated successfully.')
            except Exception as e:
                logger.error(f"Error updating bill {bill_id}: {e}")
                messages.error(request, 'Failed to update bill.')
    
    return redirect('bill_review:bill_detail', bill_id=bill_id)