# AI Data Mock-Architect

Generátor syntetických, **GDPR-safe** testovacích dát z OpenAPI/Swagger schémy. Identifikuje POST/PUT endpointy, generuje 5 sád sémanticky konzistentných mock dát na každý endpoint a ukladá ich ako JSON súbory kompatibilné s **Prism** a **Mockoon**.

---

## Ako to funguje

```
swagger.json / OpenAPI URL
        │
        ▼
 schema-architect subagent   ← parsuje POST/PUT endpointy + ich request body schémy
        │
        ▼
 data-generator subagent     ← generuje 5 GDPR-safe syntetických sád dát / endpoint
        │
        ▼
 security-auditor subagent   ← overí že žiadne PII neuniklo
        │
        ▼
 mocks/endpoints/<METHOD>_<slug>/data.json
 mocks/README.md             ← GDPR certifikácia + použitie v testoch
```

**Agent SDK pipeline** (spustenie z terminálu mimo Claude Code):
- `schema-architect` — Lead Architect, OpenAPI špecialista
- `data-generator` — Senior SDET, syntetické dáta
- `security-auditor` — Security expert, PII audit

**Fallback** (keď beží vnorene v Claude Code session):
- Priamy Anthropic API s kombinovaným Architect + SDET + Security promptom

---

## Inštalácia

```bash
pip3 install anthropic claude-agent-sdk click python-dotenv anyio
```

```bash
# .env
ANTHROPIC_API_KEY=sk-ant-api03-...
```

---

## Použitie

```bash
# Lokálny swagger.json súbor
python3 cli.py generate swagger.json

# Vzdialená OpenAPI URL
python3 cli.py generate https://petstore.swagger.io/v2/swagger.json

# Vlastný output adresár
python3 cli.py generate swagger.json --output-dir ./my-project

# Otvor mocks/ po vygenerovaní
python3 cli.py generate swagger.json --open
```

---

## Výstup

```
mocks/
├── README.md                              ← GDPR audit + návod na použitie
└── endpoints/
    ├── POST_users_register/
    │   └── data.json                      ← 5 mock sád pre POST /users/register
    ├── POST_orders/
    │   └── data.json
    └── PUT_products_id/
        └── data.json
```

### Formát `data.json`

```json
{
  "endpoint": "POST /users/register",
  "schema_summary": "...",
  "mocks": [
    {
      "id": "mock-1",
      "description": "Happy Path — všetky polia",
      "body": {
        "email": "testuser1@example.com",
        "password": "Synth@pass1",
        "firstName": "SyntheticJohn",
        "lastName": "Testuser1",
        "dateOfBirth": "1990-06-15",
        "phone": "+1-555-0101"
      }
    }
  ]
}
```

---

## GDPR-Safe Garancie

| Pole | Stratégia | Štandard |
|---|---|---|
| `email` | `@example.com` doména | RFC 2606 — IANA rezervovaná |
| `phone` | `+1-555-01xx` rozsah | NANP — rezervovaný pre fiktívne použitie |
| `firstName` / `lastName` | Prefix `Synthetic*` / `Testuser*` | Jasne syntetické |
| `dateOfBirth` | Náhodné dátumy | Bez väzby na reálne osoby |
| `userId` (UUID) | Vzorovaný `a1b2c3d4-000X-...` | Identifikovateľný ako testovací |
| Adresy | `123 Test Lane, Testville, XX` | Neexistujúce lokácie |

---

## 5 typov mock sád

| # | Typ | Účel |
|---|---|---|
| 1 | **Happy Path (Full)** | Všetky required + optional polia |
| 2 | **Happy Path (Minimal)** | Len required polia |
| 3 | **Boundary** | Hodnoty na hranici schémy (minLength, minimum) |
| 4 | **Edge Case (Overflow)** | Veľmi dlhé reťazce, max integers |
| 5 | **Edge Case (Unicode)** | Non-ASCII znaky — test encoding robustnosti |

---

## Použitie v testoch

### TypeScript / Playwright

```typescript
import mockData from '../mocks/endpoints/POST_users_register/data.json';

for (const dataset of mockData.mocks) {
  test(`POST /users/register — ${dataset.description}`, async ({ request }) => {
    const response = await request.post('/users/register', { data: dataset.body });
    expect(response.status()).toBe(201);
  });
}
```

### Python / Pytest

```python
import json, pytest

with open('mocks/endpoints/POST_orders/data.json') as f:
    data = json.load(f)

@pytest.mark.parametrize('mock', data['mocks'], ids=lambda m: m['id'])
def test_create_order(client, mock):
    response = client.post('/orders', json=mock['body'])
    assert response.status_code == 201
```

### Prism (API mocking)

```bash
npx @stoplight/prism-cli mock swagger.json
# Prism automaticky použije example hodnoty — doplň ich z data.json
```

### Mockoon

Importuj `data.json` súbory priamo do Mockoon environments.

---

## Agent Prompty

| Agent | Prompt súbor | Rola |
|---|---|---|
| `schema-architect` | `ARCHITECT.MD` | Parsovanie OpenAPI, identifikácia endpointov |
| `data-generator` | `SDET.MD` | Generovanie 5 sád syntetických dát |
| `security-auditor` | `SECURITY.MD` | PII audit, GDPR verifikácia |

---

## Multi-Agent Pipeline (mimo Claude Code)

```bash
# Otvor nový terminál
cd ~/ai-qa-projects/ai-mock-architect
python3 cli.py generate swagger.json
```

Claude Code session detekuje premenná `CLAUDECODE` — ak je nastavená, automaticky fallbackuje na priamy API.
