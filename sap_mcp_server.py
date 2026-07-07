from mcp.server.fastmcp import FastMCP
import requests
import logging
import urllib3
from datetime import datetime, timedelta

# Suppress SSL warnings for self-signed SAP certificate
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Write debug output to a log file since stdout is used by the MCP stdio protocol
logging.basicConfig(
    filename="/Users/sabate/sap-mcp/sap_mcp_debug.log",
    level=logging.DEBUG,
    format="%(asctime)s %(message)s",
    filemode="w"
)
log = logging.getLogger(__name__)

mcp = FastMCP("SAP MCP")

# READ operations use HTTP on port 5880 (no SSL required)
# WRITE operations (CSRF fetch + POST) use HTTPS on port 44388 — SAP sets the
# 'secure' flag on session cookies, so they are only sent back over HTTPS.
# Over HTTP the cookie is silently dropped, SAP gets no session on the POST,
# and rejects the CSRF token with 403.
SAP_URL = "http://sap4all.hopto.org:5880"
SAP_HTTPS_URL = "https://sap4all.hopto.org:44388"
import os
USERNAME = os.environ.get("SAP_USERNAME", "USER103")
PASSWORD = os.environ.get("SAP_PASSWORD", "")

BASE_SALES_URL = f"{SAP_URL}/sap/opu/odata/sap/API_SALES_ORDER_SRV"
BASE_BP_URL = f"{SAP_URL}/sap/opu/odata/sap/API_BUSINESS_PARTNER"
BASE_SALES_URL_HTTPS = f"{SAP_HTTPS_URL}/sap/opu/odata/sap/API_SALES_ORDER_SRV"
BASE_MATERIAL_STOCK_URL = f"{SAP_URL}/sap/opu/odata/sap/API_MATERIAL_STOCK_SRV"
BASE_PURCHASING_URL = f"{SAP_URL}/sap/opu/odata/sap/API_PURCHASING_INFORECORD_SRV"
BASE_PO_URL = f"{SAP_URL}/sap/opu/odata/sap/API_PURCHASEORDER_PROCESS_SRV"
BASE_PO_URL_HTTPS = f"{SAP_HTTPS_URL}/sap/opu/odata/sap/API_PURCHASEORDER_PROCESS_SRV"
BASE_PR_URL = f"{SAP_URL}/sap/opu/odata/sap/API_PURCHASEREQ_PROCESS_SRV"
BASE_PR_URL_HTTPS = f"{SAP_HTTPS_URL}/sap/opu/odata/sap/API_PURCHASEREQ_PROCESS_SRV"
BASE_PRODUCT_URL = f"{SAP_URL}/sap/opu/odata/sap/API_PRODUCT_SRV"

# Global persistent SAP session (used for READ operations only)
GLOBAL_SESSION = requests.Session()
GLOBAL_SESSION.auth = (USERNAME, PASSWORD)
GLOBAL_SESSION.verify = False  # SAP self-signed certificate
GLOBAL_SESSION.headers.update({
    "Accept": "application/json"
})


def fetch_csrf_token():
    """
    Fetch a fresh CSRF token over HTTPS using a dedicated session, for Sales Order writes.
    HTTPS is required because SAP sets the 'secure' flag on the session cookie —
    the cookie is only transmitted back over HTTPS, so both the fetch and the
    POST must use the same HTTPS session.
    """
    url = f"{BASE_SALES_URL_HTTPS}/A_SalesOrder?$top=1&$format=json"

    log.debug("=" * 60)
    log.debug("CSRF FETCH (SALES ORDER) — REQUEST")
    log.debug(f"  URL    : {url}")

    session = requests.Session()
    session.auth = (USERNAME, PASSWORD)
    session.verify = False
    session.headers.update({
        "Accept": "application/json",
        "x-csrf-token": "Fetch"
    })

    response = session.get(url)

    log.debug("CSRF FETCH (SALES ORDER) — RESPONSE")
    log.debug(f"  Status : {response.status_code}")
    log.debug(f"  Headers: {dict(response.headers)}")
    log.debug(f"  Cookies: {session.cookies.get_dict()}")

    csrf_token = response.headers.get("x-csrf-token")
    log.debug(f"  CSRF Token extracted: {csrf_token}")
    log.debug("=" * 60)

    response.raise_for_status()

    if not csrf_token:
        raise Exception("Unable to retrieve CSRF token — header 'x-csrf-token' missing from SAP response")

    return csrf_token, session


def fetch_csrf_token_po():
    """
    Fetch a fresh CSRF token over HTTPS for Purchase Order operations.
    """
    url = f"{BASE_PO_URL_HTTPS}/A_PurchaseOrder?$top=1&$format=json"

    log.debug("=" * 60)
    log.debug("CSRF FETCH (PO) — REQUEST")
    log.debug(f"  URL    : {url}")

    session = requests.Session()
    session.auth = (USERNAME, PASSWORD)
    session.verify = False
    session.headers.update({
        "Accept": "application/json",
        "x-csrf-token": "Fetch"
    })

    response = session.get(url)

    log.debug("CSRF FETCH (PO) — RESPONSE")
    log.debug(f"  Status : {response.status_code}")
    log.debug(f"  Headers: {dict(response.headers)}")
    log.debug(f"  Cookies: {session.cookies.get_dict()}")

    csrf_token = response.headers.get("x-csrf-token")
    log.debug(f"  CSRF Token extracted: {csrf_token}")
    log.debug("=" * 60)

    response.raise_for_status()

    if not csrf_token:
        raise Exception("Unable to retrieve CSRF token for PO — header 'x-csrf-token' missing from SAP response")

    return csrf_token, session


def fetch_csrf_token_pr():
    """
    Fetch a fresh CSRF token over HTTPS for Purchase Requisition operations.
    """
    url = f"{BASE_PR_URL_HTTPS}/A_PurchaseRequisitionHeader?$top=1&$format=json"

    log.debug("=" * 60)
    log.debug("CSRF FETCH (PR) — REQUEST")
    log.debug(f"  URL    : {url}")

    session = requests.Session()
    session.auth = (USERNAME, PASSWORD)
    session.verify = False
    session.headers.update({
        "Accept": "application/json",
        "x-csrf-token": "Fetch"
    })

    response = session.get(url)

    log.debug("CSRF FETCH (PR) — RESPONSE")
    log.debug(f"  Status : {response.status_code}")
    log.debug(f"  Headers: {dict(response.headers)}")
    log.debug(f"  Cookies: {session.cookies.get_dict()}")

    csrf_token = response.headers.get("x-csrf-token")
    log.debug(f"  CSRF Token extracted: {csrf_token}")
    log.debug("=" * 60)

    response.raise_for_status()

    if not csrf_token:
        raise Exception("Unable to retrieve CSRF token for PR — header 'x-csrf-token' missing from SAP response")

    return csrf_token, session


# ─────────────────────────────────────────────
# Sales Orders & Business Partners
# ─────────────────────────────────────────────

@mcp.tool()
def get_sales_order(sales_order_id: str):
    """
    Get sales order including line items.
    """
    url = (
        f"{BASE_SALES_URL}"
        f"/A_SalesOrder('{sales_order_id}')"
        f"?$expand=to_Item&$format=json"
    )
    response = GLOBAL_SESSION.get(url)
    response.raise_for_status()
    return response.json()


@mcp.tool()
def list_sales_orders():
    """
    List sales orders.
    """
    url = f"{BASE_SALES_URL}/A_SalesOrder?$top=5&$format=json"
    response = GLOBAL_SESSION.get(url)
    response.raise_for_status()
    return response.json()


@mcp.tool()
def get_business_partner(bp_id: str):
    """
    Get business partner.
    """
    url = (
        f"{BASE_BP_URL}"
        f"/A_BusinessPartner('{bp_id}')"
        f"?$format=json"
    )
    response = GLOBAL_SESSION.get(url)
    response.raise_for_status()
    return response.json()


@mcp.tool()
def list_business_partners():
    """
    List business partners.
    """
    url = f"{BASE_BP_URL}/A_BusinessPartner?$top=5&$format=json"
    response = GLOBAL_SESSION.get(url)
    response.raise_for_status()
    return response.json()


@mcp.tool()
def list_customers():
    """
    List customers.
    """
    url = f"{BASE_BP_URL}/A_Customer?$top=5&$format=json"
    response = GLOBAL_SESSION.get(url)
    response.raise_for_status()
    return response.json()


@mcp.tool()
def create_sales_order(
    sold_to_party: str,
    sales_order_type: str = "OR",
    sales_organization: str = "1010",
    distribution_channel: str = "10",
    division: str = "00",
    items: list[dict] = None
):
    """
    Create SAP sales order.

    Example:

    create_sales_order(
        sold_to_party="C615-A23",
        items=[
            {
                "Material": "P615-123",
                "RequestedQuantity": "10",
                "RequestedQuantityUnit": "PC"
            }
        ]
    )
    """

    if not items:
        return {
            "status": "error",
            "message": "At least one item is required"
        }

    try:
        csrf_token, session = fetch_csrf_token()

        payload = {
            "SalesOrderType": sales_order_type,
            "SalesOrganization": sales_organization,
            "DistributionChannel": distribution_channel,
            "OrganizationDivision": division,
            "SoldToParty": sold_to_party,
            "PurchaseOrderByCustomer": "Claude MCP Demo",
            "to_Item": {
                "results": [
                    {
                        "SalesOrderItem": str((idx + 1) * 10).zfill(6),
                        "Material": item["Material"],
                        "RequestedQuantity": item["RequestedQuantity"],
                        "RequestedQuantityUnit": item.get(
                            "RequestedQuantityUnit",
                            "PC"
                        )
                    }
                    for idx, item in enumerate(items)
                ]
            }
        }

        post_headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "x-csrf-token": csrf_token
        }

        log.debug("=" * 60)
        log.debug("CREATE ORDER — REQUEST")
        log.debug(f"  URL    : {BASE_SALES_URL_HTTPS}/A_SalesOrder")
        log.debug(f"  Headers: {post_headers}")
        log.debug(f"  Cookies: {session.cookies.get_dict()}")
        log.debug(f"  Payload: {payload}")

        response = session.post(
            f"{BASE_SALES_URL_HTTPS}/A_SalesOrder",
            headers=post_headers,
            verify=False,
            json=payload
        )

        log.debug("CREATE ORDER — RESPONSE")
        log.debug(f"  Status : {response.status_code}")
        log.debug(f"  Headers: {dict(response.headers)}")
        log.debug(f"  Body   : {response.text}")
        log.debug("=" * 60)

        if not response.ok:
            return {
                "status": "error",
                "http_status": response.status_code,
                "details": response.text
            }

        try:
            response_data = response.json()
            sales_order_id = response_data.get("d", {}).get("SalesOrder", "unknown")
        except Exception:
            response_data = response.text
            sales_order_id = "unknown"

        return {
            "status": "success",
            "http_status": response.status_code,
            "message": f"Sales order {sales_order_id} created successfully",
            "response": response_data
        }

    except Exception as e:
        log.debug(f"EXCEPTION: {str(e)}")
        return {
            "status": "error",
            "message": str(e)
        }


# ─────────────────────────────────────────────
# Stock
# ─────────────────────────────────────────────

@mcp.tool()
def get_stock(
    material: str,
    plant: str = "1010"
):
    """
    Get current stock level for a material at a given plant.

    Returns unrestricted stock quantity and unit of measure.
    Calls the navigation property directly (not via $expand, which times out
    on this service).

    Example:

    get_stock(material="198", plant="1010")
    """
    url = (
        f"{BASE_MATERIAL_STOCK_URL}"
        f"/A_MaterialStock('{material}')"
        f"/to_MatlStkInAcctMod"
        f"?$format=json"
    )

    log.debug("=" * 60)
    log.debug("GET STOCK — REQUEST")
    log.debug(f"  URL    : {url}")

    response = GLOBAL_SESSION.get(url)

    log.debug("GET STOCK — RESPONSE")
    log.debug(f"  Status : {response.status_code}")
    log.debug(f"  Body   : {response.text}")
    log.debug("=" * 60)

    response.raise_for_status()
    data = response.json()

    entries = data.get("d", {}).get("results", [])
    plant_entries = [e for e in entries if e.get("Plant") == plant]

    if not plant_entries:
        return {
            "material": material,
            "plant": plant,
            "unrestricted_stock": 0,
            "unit": "unknown",
            "message": f"No stock found for material {material} at plant {plant}"
        }

    total = sum(
        float(e.get("MatlWrhsStkQtyInMatlBaseUnit", 0))
        for e in plant_entries
    )
    unit = plant_entries[0].get("MaterialBaseUnit", "")

    return {
        "material": material,
        "plant": plant,
        "unrestricted_stock": total,
        "unit": unit,
        "detail": plant_entries
    }


# ─────────────────────────────────────────────
# Purchasing Info Record
# ─────────────────────────────────────────────

@mcp.tool()
def get_purchasing_info_record(
    material: str,
    supplier: str,
    purchasing_org: str = "1010"
):
    """
    Get purchasing info record for a material/supplier combination.

    Returns info record number, price conditions, and order unit.

    Example:

    get_purchasing_info_record(
        material="198",
        supplier="10300006",
        purchasing_org="1010"
    )
    """
    url = (
        f"{BASE_PURCHASING_URL}"
        f"/A_PurchasingInfoRecord"
        f"?$filter=Material eq '{material}'"
        f" and Supplier eq '{supplier}'"
        f" and PurchasingOrganization eq '{purchasing_org}'"
        f"&$expand=to_PurchasingInfoRecordValidity"
        f"&$format=json"
    )

    log.debug("=" * 60)
    log.debug("GET INFO RECORD — REQUEST")
    log.debug(f"  URL    : {url}")

    response = GLOBAL_SESSION.get(url)

    log.debug("GET INFO RECORD — RESPONSE")
    log.debug(f"  Status : {response.status_code}")
    log.debug(f"  Body   : {response.text}")
    log.debug("=" * 60)

    response.raise_for_status()
    data = response.json()

    results = data.get("d", {}).get("results", [])

    if not results:
        return {
            "status": "not_found",
            "message": f"No info record found for material {material}, supplier {supplier}, purchasing org {purchasing_org}"
        }

    record = results[0]

    return {
        "status": "found",
        "info_record": record.get("PurchasingInfoRecord"),
        "material": record.get("Material"),
        "supplier": record.get("Supplier"),
        "purchasing_org": record.get("PurchasingOrganization"),
        "order_unit": record.get("PurchaseOrderUnit"),
        "material_group": record.get("MaterialGroup"),
        "detail": record
    }


# ─────────────────────────────────────────────
# Purchase Order
# ─────────────────────────────────────────────

@mcp.tool()
def create_purchase_order(
    supplier: str,
    material: str,
    quantity: str,
    unit: str = "KG",
    plant: str = "1010",
    purchasing_org: str = "1010",
    purchasing_group: str = "001",
    company_code: str = "1010"
):
    """
    Create a SAP Purchase Order for a material from a supplier.

    Example:

    create_purchase_order(
        supplier="10300006",
        material="198",
        quantity="50",
        unit="KG",
        plant="1010"
    )
    """
    try:
        csrf_token, session = fetch_csrf_token_po()

        payload = {
            "CompanyCode": company_code,
            "PurchaseOrderType": "NB",
            "Supplier": supplier,
            "PurchasingOrganization": purchasing_org,
            "PurchasingGroup": purchasing_group,
            "DocumentCurrency": "EUR",
            "to_PurchaseOrderItem": {
                "results": [
                    {
                        "PurchaseOrderItem": "00010",
                        "Plant": plant,
                        "Material": material,
                        "OrderQuantity": quantity,
                        "PurchaseOrderQuantityUnit": unit,
                        "AccountAssignmentCategory": "",
                        "ItemCategory": ""
                    }
                ]
            }
        }

        post_headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "x-csrf-token": csrf_token
        }

        log.debug("=" * 60)
        log.debug("CREATE PO — REQUEST")
        log.debug(f"  URL    : {BASE_PO_URL_HTTPS}/A_PurchaseOrder")
        log.debug(f"  Headers: {post_headers}")
        log.debug(f"  Cookies: {session.cookies.get_dict()}")
        log.debug(f"  Payload: {payload}")

        response = session.post(
            f"{BASE_PO_URL_HTTPS}/A_PurchaseOrder",
            headers=post_headers,
            verify=False,
            json=payload
        )

        log.debug("CREATE PO — RESPONSE")
        log.debug(f"  Status : {response.status_code}")
        log.debug(f"  Headers: {dict(response.headers)}")
        log.debug(f"  Body   : {response.text}")
        log.debug("=" * 60)

        if not response.ok:
            return {
                "status": "error",
                "http_status": response.status_code,
                "details": response.text
            }

        try:
            response_data = response.json()
            po_number = response_data.get("d", {}).get("PurchaseOrder", "unknown")
        except Exception:
            response_data = response.text
            po_number = "unknown"

        return {
            "status": "success",
            "http_status": response.status_code,
            "message": f"Purchase order {po_number} created successfully for {quantity} {unit} of material {material} from supplier {supplier}",
            "response": response_data
        }

    except Exception as e:
        log.debug(f"EXCEPTION: {str(e)}")
        return {
            "status": "error",
            "message": str(e)
        }


# ─────────────────────────────────────────────
# Purchase Requisition (autonomous procurement)
# ─────────────────────────────────────────────

@mcp.tool()
def create_purchase_requisition(
    material: str,
    quantity: str,
    unit: str = "KG",
    plant: str = "1010",
    purchasing_group: str = "001",
    requisition_reason: str = "Autonomous replenishment by Claude MCP"
):
    """
    Create a SAP Purchase Requisition for a material.

    A Purchase Requisition is a request to procure a material — it does NOT
    commit spend directly. A buyer reviews and converts it to a Purchase Order.
    This is the recommended autonomous procurement pattern: AI triggers the need,
    human approves the spend.

    Vendor and price are auto-assigned by SAP source determination
    (SourceDetermination=true) based on the purchasing info record for the
    material/plant — no need to look up or pass a supplier.

    Example:

    create_purchase_requisition(
        material="198",
        quantity="70",
        unit="KG",
        plant="1010"
    )
    """
    try:
        csrf_token, session = fetch_csrf_token_pr()

        delivery_dt = datetime.utcnow() + timedelta(days=7)
        delivery_ts = int(delivery_dt.replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)
        delivery_date_sap = f"/Date({delivery_ts})/"

        payload = {
            "PurchaseRequisitionType": "NB",
            "PurReqnDescription": requisition_reason[:40],
            "SourceDetermination": True,
            "to_PurchaseReqnItem": {
                "results": [
                    {
                        "PurchaseRequisitionItem": "00010",
                        "PurchaseRequisitionItemText": requisition_reason[:40],
                        "Material": material,
                        "RequestedQuantity": quantity,
                        "BaseUnit": unit,
                        "Plant": plant,
                        "PurchasingGroup": purchasing_group,
                        "DeliveryDate": delivery_date_sap
                    }
                ]
            }
        }

        post_headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "x-csrf-token": csrf_token
        }

        log.debug("=" * 60)
        log.debug("CREATE PR — REQUEST")
        log.debug(f"  URL    : {BASE_PR_URL_HTTPS}/A_PurchaseRequisitionHeader")
        log.debug(f"  Headers: {post_headers}")
        log.debug(f"  Cookies: {session.cookies.get_dict()}")
        log.debug(f"  Payload: {payload}")

        response = session.post(
            f"{BASE_PR_URL_HTTPS}/A_PurchaseRequisitionHeader",
            headers=post_headers,
            verify=False,
            json=payload
        )

        log.debug("CREATE PR — RESPONSE")
        log.debug(f"  Status : {response.status_code}")
        log.debug(f"  Headers: {dict(response.headers)}")
        log.debug(f"  Body   : {response.text}")
        log.debug("=" * 60)

        if not response.ok:
            return {
                "status": "error",
                "http_status": response.status_code,
                "details": response.text
            }

        try:
            response_data = response.json()
            pr_number = response_data.get("d", {}).get("PurchaseRequisition", "unknown")
        except Exception:
            response_data = response.text
            pr_number = "unknown"

        return {
            "status": "success",
            "http_status": response.status_code,
            "message": f"Purchase requisition {pr_number} created for {quantity} {unit} of material {material} at plant {plant}",
            "purchase_requisition": pr_number,
            "response": response_data
        }

    except Exception as e:
        log.debug(f"EXCEPTION: {str(e)}")
        return {
            "status": "error",
            "message": str(e)
        }


# ─────────────────────────────────────────────
# Material Replenishment Rules (MRP master data)
# ─────────────────────────────────────────────

@mcp.tool()
def get_material_replenishment_rules(
    material: str,
    plant: str = "1010"
):
    """
    Read replenishment rules for a material at a given plant from SAP MRP master data.

    Returns reorder point, maximum stock level, MRP type and lot size procedure.
    Claude uses these values to autonomously decide whether to replenish and
    how much to order.

    Logic:
        if current_stock < reorder_point:
            order_quantity = maximum_stock - current_stock

    Example:

    get_material_replenishment_rules(material="198", plant="1010")
    """
    url = (
        f"{BASE_PRODUCT_URL}"
        f"/A_ProductSupplyPlanning(Product='{material}',Plant='{plant}')"
        f"?$select=Product,Plant,MRPType,MRPResponsible,ReorderThresholdQuantity,"
        f"MaximumStockQuantity,LotSizingProcedure,BaseUnit"
        f"&$format=json"
    )

    log.debug("=" * 60)
    log.debug("GET REPLENISHMENT RULES — REQUEST")
    log.debug(f"  URL    : {url}")

    response = GLOBAL_SESSION.get(url)

    log.debug("GET REPLENISHMENT RULES — RESPONSE")
    log.debug(f"  Status : {response.status_code}")
    log.debug(f"  Body   : {response.text}")
    log.debug("=" * 60)

    response.raise_for_status()
    data = response.json()
    record = data.get("d", {})

    reorder_point = float(record.get("ReorderThresholdQuantity", 0) or 0)
    maximum_stock = float(record.get("MaximumStockQuantity", 0) or 0)
    mrp_type = record.get("MRPType", "")
    lot_size = record.get("LotSizingProcedure", "")
    unit = record.get("BaseUnit", "KG")

    return {
        "material": material,
        "plant": plant,
        "mrp_type": mrp_type,
        "lot_sizing_procedure": lot_size,
        "reorder_point": reorder_point,
        "maximum_stock": maximum_stock,
        "unit": unit,
        "replenishment_logic": f"If stock < {reorder_point} {unit}, order up to {maximum_stock} {unit}"
    }


@mcp.tool()
def list_materials_for_replenishment(
    plant: str = "1010"
):
    """
    List all materials at a plant configured for reorder-point planning (MRP Type VB)
    that have both a reorder point and a maximum stock level defined.

    Returns each material with its reorder point, maximum stock level and unit.
    Claude uses this to autonomously loop through all materials, check stock,
    and create purchase requisitions where needed — without any material number
    being given by the user.

    Full autonomous replenishment flow:
        1. list_materials_for_replenishment(plant) → list of materials + rules
        2. For each material: get_stock(material, plant)
        3. If stock < reorder_point: create_purchase_requisition(material, max_stock - stock)

    Materials with no maximum stock level configured are excluded, since an
    order quantity cannot be reliably calculated for them from master data alone.

    Example:

    list_materials_for_replenishment(plant="1010")
    """
    url = (
        f"{BASE_PRODUCT_URL}"
        f"/A_ProductSupplyPlanning"
        f"?$filter=Plant eq '{plant}' and MRPType eq 'VB'"
        f"&$select=Product,Plant,MRPType,MRPResponsible,"
        f"ReorderThresholdQuantity,MaximumStockQuantity,"
        f"LotSizingProcedure,BaseUnit"
        f"&$format=json"
    )

    log.debug("=" * 60)
    log.debug("LIST MATERIALS FOR REPLENISHMENT — REQUEST")
    log.debug(f"  URL    : {url}")

    response = GLOBAL_SESSION.get(url)

    log.debug("LIST MATERIALS FOR REPLENISHMENT — RESPONSE")
    log.debug(f"  Status : {response.status_code}")
    log.debug(f"  Body   : {response.text[:1000]}")
    log.debug("=" * 60)

    response.raise_for_status()
    data = response.json()
    results = data.get("d", {}).get("results", [])

    materials = []
    skipped = []
    for r in results:
        reorder_point = float(r.get("ReorderThresholdQuantity", 0) or 0)
        maximum_stock = float(r.get("MaximumStockQuantity", 0) or 0)
        material_id = r.get("Product")

        # Only include materials with BOTH a reorder point and a maximum stock
        # level configured — otherwise an order quantity cannot be calculated
        # reliably from master data alone.
        if reorder_point > 0 and maximum_stock > 0:
            materials.append({
                "material": material_id,
                "plant": r.get("Plant"),
                "mrp_type": r.get("MRPType"),
                "mrp_controller": r.get("MRPResponsible"),
                "reorder_point": reorder_point,
                "maximum_stock": maximum_stock,
                "lot_sizing": r.get("LotSizingProcedure"),
                "unit": r.get("BaseUnit"),
                "replenishment_logic": f"If stock < {reorder_point}, order up to {maximum_stock} {r.get('BaseUnit', '')}"
            })
        else:
            skipped.append({
                "material": material_id,
                "reason": "Missing reorder point and/or maximum stock level — cannot calculate order quantity"
            })

    return {
        "plant": plant,
        "total_materials_with_vb_planning": len(results),
        "actionable_materials": len(materials),
        "materials": materials,
        "skipped_materials": skipped
    }


mcp.run()
