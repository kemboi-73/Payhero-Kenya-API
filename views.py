import json
import logging
import requests
from django.urls import reverse
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse, HttpResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt

# Local Imports
from posApp.models import Sales
from posApp.utils import get_shop, shop_required

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════
# PAYHERO / M-PESA CHECKOUT
# ══@login_required
@shop_required
def initiate_payhero(request):
    """Initiates an STK Push to the customer's phone via PayHero API."""
    if request.method != 'POST':
        return JsonResponse({'status': 'failed', 'msg': 'Invalid method.'}, status=405)

    shop = get_shop(request)
    sale_id = request.POST.get('sale_id')
    
    # FIX: Update these keys to match what JS is sending
    phone = request.POST.get('phone_number', '').strip()
    amount = request.POST.get('grand_total')

    if not all([sale_id, phone, amount]):
        return JsonResponse({'status': 'failed', 'msg': 'Missing required fields.'})

    sale = get_object_or_404(Sales, id=sale_id, shop=shop)

    # Clean phone number (e.g., convert 07... to 2547...)
    if phone.startswith('0'):
        phone = '254' + phone[1:]
    elif phone.startswith('+'):
        phone = phone[1:]

    
        channel_id = shop.payhero_channel_id
        username = shop.payhero_username
        password = shop.payhero_password
        
        url = "https://backend.payhero.co.ke/api/v2/payments"
        payload = {
            "amount": float(amount),
            "phone_number": phone,
            "channel_id": channel_id,
            "provider": "m-pesa",
            
          
            "external_reference": f"SALE-{sale.id}-SHOP-{shop.id}",
            
            # FIX 2: Dynamic callback URL to avoid 404 errors
            "callback_url": f"{settings.SITE_URL}{reverse('payhero_callback')}"
        }
        
        response = requests.post(url, json=payload, auth=(username, password), timeout=10)
        data = response.json()
        # print("--- PAYHERO RAW RESPONSE ---", data)

        if response.status_code in [200, 201] and data.get('success'):
            sale.payment_status = 'pending'
            sale.save(update_fields=['payment_status'])
            
            return JsonResponse({
                'success': True,
                'status': 'success',
                'msg': 'STK Push sent to customer.',
                
                # FIX 3: Match PayHero's exact PascalCase capitalization
                'CheckoutRequestID': data.get('CheckoutRequestID', ''),
                'reference': data.get('reference', sale.code)
            })
        else:
            return JsonResponse({'status': 'failed', 'msg': data.get('message', 'API Error')})

    except requests.exceptions.RequestException as e:
        logger.error(f"PayHero Network Error: {e}")
        return JsonResponse({'status': 'failed', 'msg': 'Failed to connect to payment gateway.'})
