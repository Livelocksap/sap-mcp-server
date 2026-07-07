# SAP MCP Server

A custom MCP (Model Context Protocol) server connecting Claude to SAP S/4HANA via standard published OData APIs.

Built as a proof of concept for **Autonomous ERP** — demonstrating that AI agents can operate SAP transactional processes without SAP Joule, BTP, or a cloud migration.

## What it does

- Reads stock levels from SAP
- Reads MRP replenishment rules from material master
- Lists all materials configured for reorder-point planning at a plant
- Creates Purchase Requisitions autonomously when stock falls below reorder point
- Creates Sales Orders
- Reads Business Partners and Customers
- Creates Purchase Orders

## Architecture

```
Claude (AI agent)
    ↓
MCP Server (this Python file)
    ↓
SAP OData APIs (published, standard)
    ↓
SAP S/4HANA On-Premise
```

## SAP APIs used

All APIs are published on SAP Business Accelerator Hub:

| API | Purpose |
|---|---|
| `API_SALES_ORDER_SRV` | Sales order read/create |
| `API_BUSINESS_PARTNER` | Business partner / customer read |
| `API_MATERIAL_STOCK_SRV` | Stock level read |
| `API_PURCHASEREQ_PROCESS_SRV` | Purchase requisition create |
| `API_PURCHASEORDER_PROCESS_SRV` | Purchase order create |
| `API_PRODUCT_SRV` | Material/MRP master data read |

## Setup

1. Install dependencies:
```bash
pip install mcp requests urllib3
```

2. Activate the OData services in SAP via `/IWFND/MAINT_SERVICE` — assign ICF Node (SAP Gateway OData V2) and System Alias (LOCAL) for each service.

3. Update credentials and SAP hostname in `sap_mcp_server.py`

4. Configure in Claude Desktop `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "sap": {
      "command": "python",
      "args": ["path/to/sap_mcp_server.py"]
    }
  }
}
```

## Key technical notes

- **Reads use HTTP** (port 5880), **writes use HTTPS** (port 44388) — SAP sets the `secure` flag on session cookies, so CSRF tokens fetched over HTTP are silently dropped on POST
- Each write operation fetches its own CSRF token over HTTPS in a dedicated session
- Stock API uses direct navigation property (`/to_MatlStkInAcctMod`) instead of `$expand` to avoid timeouts
- All debug output goes to a log file (not stdout, which is consumed by MCP stdio protocol)

## LinkedIn series

This server was built as part of a public LinkedIn series on Autonomous ERP and AI in SAP:
- [Autonomous SAP S/4HANA demo](https://www.linkedin.com/in/albertosabate/)

## Author

Alberto Sabate — SAP & AI Consultant  
[linkedin.com/in/albertosabate](https://linkedin.com/in/albertosabate)  
[livelock.pl](https://livelock.pl)
