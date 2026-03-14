# GDPR-Safe Synthetic Mock Data

## Overview

This directory contains **synthetic mock datasets** generated from the E-Commerce API OpenAPI 3.0 specification. Each POST/PUT endpoint has **5 mock payloads** designed for testing across happy paths, boundary conditions, and edge cases.

## Directory Structure

```
mocks/
├── README.md
└── endpoints/
    ├── POST_users_register/
    │   └── data.json          # 5 datasets for POST /users/register
    ├── POST_orders/
    │   └── data.json          # 5 datasets for POST /orders
    └── PUT_products_id/
        └── data.json          # 5 datasets for PUT /products/{id}
```

## GDPR Compliance Verification

### PII Audit Results: ✅ PASS — NO PII DETECTED

Every field that *could* contain PII was replaced with a **verifiably synthetic** value:

| Field | Strategy | Standard |
|---|---|---|
| `email` | `@example.com` domain | RFC 2606 — IANA reserved, not routable |
| `phone` | `+1-555-01xx` range | NANP — reserved for fictional use |
| `firstName` / `lastName` | Prefixed `Synthetic*` / `Testuser*` | Obviously non-real, non-attributable |
| `dateOfBirth` | Arbitrary dates | No linkage to real individuals |
| `userId` (UUID) | Patterned `a1b2c3d4-000X-...` | Synthetic, no DB mapping |
| `shippingAddress` | Fictional cities/streets (`Testville`, `123 Test Lane`) | Non-existent locations, `XX` country code |
| `productId` | Prefixed `PROD-TEST-*` | Clearly synthetic identifiers |

### What This Means

- **Safe for CI/CD:** These mocks can be committed to version control and used in pipelines without GDPR risk.
- **Safe for Logs:** No real person's data will appear in test logs or error reports.
- **Safe for Sharing:** These files can be shared across teams, contractors, and environments.

## Dataset Design Strategy

Each endpoint includes 5 datasets covering:

| # | Type | Purpose |
|---|---|---|
| 1 | **Happy Path (Full)** | All required + optional fields with valid values |
| 2 | **Happy Path (Minimal)** | Only required fields / partial update |
| 3 | **Boundary** | Values at schema-defined minimums (minLength, minimum: 0) |
| 4 | **Edge Case (Overflow)** | Very long strings, max integers, high decimals |
| 5 | **Edge Case (Unicode)** | Non-ASCII characters to test encoding robustness |

## Usage in Tests

### TypeScript / Playwright Example

```typescript
import registerData from '../mocks/endpoints/POST_users_register/data.json';

for (const dataset of registerData.datasets) {
  test(`POST /users/register — ${dataset.description}`, async ({ request }) => {
    const response = await request.post('/users/register', {
      data: dataset.body,
    });
    expect(response.status()).toBe(201);
  });
}
```

### Python / Pytest Example

```python
import json, pytest

with open('mocks/endpoints/POST_orders/data.json') as f:
    orders_data = json.load(f)

@pytest.mark.parametrize('dataset', orders_data['datasets'], ids=lambda d: d['id'])
def test_create_order(client, dataset):
    response = client.post('/orders', json=dataset['body'])
    assert response.status_code == 201
```

## Security Notes

- **Passwords** in `POST /users/register` mocks are synthetic test strings. They are **not** derived from any real credential list or breach database.
- The `XX` country code is used intentionally as it is unassigned by ISO 3166 — preventing accidental geo-attribution.
- All UUIDs follow v4 format but use a deterministic pattern (`a1b2c3d4-000X-4000-8000-...`) to make them easily identifiable as test data in logs.

## TODO

- `TODO:` Define expected HTTP response codes per dataset to enable assertion scaffolding.
- `TODO:` Add negative/invalid datasets (missing required fields, malformed emails, negative quantities) as a separate `negative.json` per endpoint.
- `TODO:` Integrate with a schema validator (e.g., `ajv`) to auto-verify mock payloads match the OpenAPI spec at CI time.
- `TODO:` Define load/performance test variants with higher cardinality if k6 or Artillery testing is planned.
