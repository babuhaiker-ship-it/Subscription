# Monero (XMR) Payment Gateway API & Telegram Bot

An asynchronous **Monero (XMR) Payment Gateway API** and Telegram Bot built for deployment on **Render.com**.

## Features

- **Monero Payment Gateway REST API** built with FastAPI and Uvicorn.
- **Dynamic XMR/USD Price Rates**: Real-time conversion using CoinGecko and Kraken APIs.
- **Subaddress & Primary Address Support**: Works with standard Monero primary addresses (`4...`) or subaddresses (`8...`).
- **Interactive OpenAPI Documentation**: Swagger UI at `/docs` and ReDoc at `/redoc`.
- **Render.com Compatibility**: Healthcheck endpoint (`/health`) and dynamic `$PORT` binding.
- **Automatic Webhooks**: Sends JSON POST notifications to client callback URLs when payments are confirmed.
- **Telegram Bot Integration**: Full multi-plan premium Telegram bot with interactive inline payment handling.

---

## API Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/health` | Service health status & MongoDB ping |
| `POST` | `/api/v1/invoices/create` | Create a new Monero payment invoice |
| `GET` | `/api/v1/invoices/{invoice_id}` | Retrieve invoice status and details |
| `GET` | `/api/v1/invoices` | List invoices with optional status filtering |
| `POST` | `/api/v1/invoices/{invoice_id}/verify` | Verify payment and trigger optional webhook |

### Example Invoice Creation Payload (`POST /api/v1/invoices/create`)

```json
{
  "amount_usd": 10.00,
  "order_id": "ORDER_12345",
  "description": "Premium Subscription",
  "callback_url": "https://your-domain.com/webhook",
  "expiry_minutes": 60
}
```

### Example Response

```json
{
  "success": true,
  "invoice": {
    "invoice_id": "65f01234abcd5678ef901234",
    "order_id": "ORDER_12345",
    "address": "888tNkZrPNydR3a...",
    "xmr_amount": 0.06250000,
    "price_usd": 10.00,
    "xmr_rate_usd": 160.00,
    "status": "pending",
    "is_claimed": false,
    "txid": null,
    "qr_code_url": "https://api.qrserver.com/v1/create-qr-code/?size=300x300&data=monero:888tNkZrPNydR3a...?tx_amount=0.062500",
    "created_at": "2025-01-01T00:00:00+00:00",
    "expires_at": "2025-01-01T01:00:00+00:00",
    "callback_url": "https://your-domain.com/webhook"
  }
}
```

---

## Deploying on Render.com

1. **Create a new Web Service on Render.com**
2. **Environment & Runtime**: Choose **Docker** or **Python 3.11+**.
3. **Set Environment Variables**:
   - `MONGO_URI`: Your MongoDB connection string.
   - `MONERO_ADDRESS`: Your primary Monero address (`4...`) or default subaddress.
   - `MONERO_RPC_URL`: *(Optional)* `http://your-monero-wallet-rpc:18082/json_rpc`
   - `MONERO_RPC_USER`: *(Optional)* RPC Username
   - `MONERO_RPC_PASSWORD`: *(Optional)* RPC Password
   - `API_ID`, `API_HASH`, `BOT_TOKEN`: *(Optional for Telegram Bot)*
4. **Health Check Path**: Set to `/health`.
5. **Start Command**:
   ```bash
   uvicorn api:app --host 0.0.0.0 --port $PORT
   ```

---

## Running Locally

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Run API server:
   ```bash
   uvicorn api:app --host 0.0.0.0 --port 8080 --reload
   ```
3. Open `http://localhost:8080/docs` in your browser.
