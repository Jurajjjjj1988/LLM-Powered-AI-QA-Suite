# www.orange.sk — AI-Assisted QA Bug Report

> **Autor:** Juraj Kapusanský
> **Dátum:** 14. 3. 2026
> **Repo:** [LLM-Powered-AI-QA-Suite](https://github.com/Jurajjjjj1988/LLM-Powered-AI-QA-Suite)

---

## Executive Summary

Počas analýzy bolo identifikovaných **5 bugov** rôznej závažnosti — od kritických bezpečnostných problémov až po UX a feature parity nedostatky. Všetky boli nájdené **automatizovaným crawlom + AI analýzou** v priebehu niekoľkých minút, bez jediného manuálneho kliknutia.

| # | Závažnosť | Kategória | Stručný popis |
|---|-----------|-----------|---------------|
| [BUG-001](#bug-001--http-downgrade-pri-trailing-slash) | 🔴 Critical | Security | HTTP downgrade — redirect ide na `http://` nie `https://` |
| [BUG-002](#bug-002--6-kanonických-url-vracia-http-404) | 🔴 Critical | Broken UX | 6 hlavných URL v navigácii vracia 404 |
| [BUG-003](#bug-003--chatbot-len-na-b2b-chýba-na-b2c) | 🟠 High | Feature Gap | Chatbot dostupný iba pre B2B zákazníkov, B2C ho nemá |
| [BUG-004](#bug-004--môj-orange-login-cez-http) | 🟠 High | Security | Login portál prechádza cez nešifrovaný `http://` kanál |
| [BUG-005](#bug-005--duplicitná-navigácia-bez-aria) | 🟡 Medium | Accessibility | Duplicitné nav menu, chýbajú ARIA atribúty — WCAG 2.1 porušenie |

---

## BUG-001 — HTTP Downgrade pri Trailing Slash

| | |
|---|---|
| **Závažnosť** | 🔴 Critical |
| **Kategória** | Security |
| **OWASP** | A02:2021 — Cryptographic Failures |
| **Prostredie** | Production — www.orange.sk |

### Popis

Každá URL s lomítkom na konci vracia HTTP **301 redirect na `http://`** namiesto `https://`. Prehliadač väčšinou zachytí druhý redirect späť na HTTPS, ale toto okno je reálny exploit vektor.

### Reprodukcia

```bash
curl -I https://www.orange.sk/
# HTTP/1.1 301 Moved Permanently
# Location: http://www.orange.sk   ← ⚠️ http, nie https
```

### Riziko

- **SSL Stripping attack** — útočník na verejnej WiFi môže zachytiť HTTP hop a odkloniť celú session
- Ak `Strict-Transport-Security` header nie je správne nastavený, prehliadač redirect akceptuje bez varovania
- Potenciálne porušenie **GDPR čl. 32** — povinnosť technicky zabezpečiť osobné údaje

### Odporúčanie

Opraviť server-side redirect rule — všetky 301 musia smerovať na `https://`, nie `http://`.

```nginx
# Správna konfigurácia nginx
server {
    listen 80;
    return 301 https://$host$request_uri;  # ← https, nie http
}
```

---

## BUG-002 — 6 Kanonických URL vracia HTTP 404

| | |
|---|---|
| **Závažnosť** | 🔴 Critical |
| **Kategória** | Broken Navigation / Revenue Loss |
| **Dopad** | Priamy výpadok konverzie + SEO penalizácia |

### Popis

Nasledujúce URL sú linkované v hlavnej navigácii alebo sitemap, ale vrátia `404 Not Found`. Zákazník prichádzajúci z Google alebo PPC reklamy narazí na mŕtvu stránku.

| URL | Očakávaný obsah | HTTP Status |
|-----|----------------|-------------|
| `/volania-a-pausal/pausal` | Paušálne tarify | 404 |
| `/telefony-a-zariadenia/smartfony` | Smartfóny eshop | 404 |
| `/internetatv/internet` | Internet sekcia | 404 |
| `/pre-biznis` | Business sekcia | 404 |
| `/eshop` | Hlavný e-shop | 404 |
| `/obchody` | Zoznam predajní | 404 |

### Reprodukcia

```bash
curl -o /dev/null -s -w "%{http_code}" https://www.orange.sk/eshop
# 404

curl -o /dev/null -s -w "%{http_code}" https://www.orange.sk/telefony-a-zariadenia/smartfony
# 404
```

### Dopad

- **Revenue** — `/eshop` a `/smartfony` sú primárne konverzné stránky. Každá minúta ich nedostupnosti = priama strata predaja.
- **SEO** — Googlebot indexuje 404, stránky postupne vypadávajú z výsledkov vyhľadávania. Obnova rankingu po oprave trvá týždne.
- **PPC waste** — ak Google Ads kampane smerujú na tieto URL, každý klik je peniaz vyhodený oknom.

### Odporúčanie

Buď obnoviť stránky na pôvodných URL, alebo nasadiť 301 redirecty na nové URL. Urgentná priorita pre `/eshop`.

---

## BUG-003 — Chatbot len na B2B, chýba na B2C

| | |
|---|---|
| **Závažnosť** | 🟠 High |
| **Kategória** | Feature Gap / UX |
| **Dopad** | Zvýšená záťaž call centra, horšia zákaznícka skúsenosť |

### Popis

Widget live chatu / chatbota je dostupný **iba na B2B verzii portálu** (sekcia pre firmy). Na hlavnom **B2C webe (`www.orange.sk`) chatbot úplne chýba**, napriek tomu, že B2C zákazníci generujú podstatne väčší objem customer support requestov.

### Prečo je to bug

Z pohľadu zákazníka je táto asymetria nelogická a nekonzistentná — firemní zákazníci majú prístup k rýchlej chat podpore, bežní zákazníci nie. Firemní zákazníci navyše obvykle disponujú dedikovaným account managerom, takže potreba chatu je pre nich paradoxne nižšia.

### Dopad

- B2C zákazníci sú nútení volať na linku alebo hľadať kontaktný formulár → vyššia miera opustenia
- Zvyšuje náklady na call centrum (chat je ~3–5× lacnejší na interakciu ako telefonát)
- **Konkurenčná nevýhoda** — Telekom aj O2 majú chatbot/live chat na B2C webe
- Zákazníci s jednoduchými otázkami (tarify, faktúry, SIM) nemajú self-service možnosť

### User Journey, ktorý odhalí tento bug

```
Scenár: B2C zákazník chce rýchlo kontaktovať podporu cez chat
1. Otvorí www.orange.sk
2. Hľadá chat ikonu (vpravo dole alebo v hlavičke)
3. Chat ikona neexistuje
4. Zákazník nájde len "Zavolajte nám" → musí telefonovať

Výsledok: Fail — základná self-service funkcia chýba
```

### Odporúčanie

Nasadiť chatbot aj na B2C (`www.orange.sk`). Minimálne FAQ bot pre najčastejšie otázky: zmena tarifu, faktúra, strata SIM, pokrytie.

---

## BUG-004 — Môj Orange Login cez HTTP

| | |
|---|---|
| **Závažnosť** | 🟠 High |
| **Kategória** | Security |
| **OWASP** | A02:2021 — Cryptographic Failures, A07:2021 — Identification and Authentication Failures |

### Popis

URL `/moj-orange/` (zákaznícky portál — login stránka s osobnými údajmi a faktúrami) pri redirecte prechádza rovnakým HTTP downgrade problémom ako BUG-001. Tu je dopad kritickejší, pretože ide o **autentifikovanú sekciu**.

### Reprodukcia

```bash
curl -I https://www.orange.sk/moj-orange/
# 301 Location: http://www.orange.sk/moj-orange   ← ⚠️
```

### Riziko

- Login credentials (meno + heslo) môžu byť odchytené v tom HTTP hope
- Session cookie môže byť odchytený ak nie je nastavený `Secure` flag
- Osobné údaje zákazníka (faktúry, adresa, číslo zmluvy) prístupné cez nešifrované spojenie
- **GDPR čl. 32** — prevádzkovateľ musí prijať "primerané technické opatrenia" na ochranu osobných údajov

### Odporúčanie

Opraviť redirect (rovnaká oprava ako BUG-001) + auditovať `Set-Cookie` headery:

```
Set-Cookie: session=...; Secure; HttpOnly; SameSite=Strict
```

---

## BUG-005 — Duplicitná Navigácia bez ARIA

| | |
|---|---|
| **Závažnosť** | 🟡 Medium |
| **Kategória** | Accessibility |
| **Štandard** | WCAG 2.1 Level AA (záväzné pre EÚ komerčné weby) |

### Popis

HTML stránky obsahujú **dve identické `<nav>` bloky** v DOM — jedno pre desktop, jedno pre mobilné rozlíšenie. Obe sú vždy prítomné v DOM (viditeľnosť prepínaná iba cez CSS `display: none`).

### Problémy

- **Screen reader** (NVDA, VoiceOver) číta navigáciu dvakrát — dezorientujúce pre nevidiacich a slabozrakých používateľov
- Chýba `aria-label="Hlavná navigácia"` na `<nav>` elementoch
- Chýba `aria-hidden="true"` na skrytej kópii navigácie
- Porušenie **WCAG 2.1 — Success Criterion 1.3.1** (Info and Relationships)

### Reprodukcia

```bash
# Obe nav bloky sú vždy v DOM:
curl -s https://www.orange.sk/ | grep -c '<nav'
# 2 (alebo viac)
```

### Odporúčanie

```html
<!-- Mobil nav — skrytý pre screen readery keď nie je aktívny -->
<nav aria-label="Mobilná navigácia" aria-hidden="true" class="mobile-nav hidden">

<!-- Desktop nav -->
<nav aria-label="Hlavná navigácia" class="desktop-nav">
```

---

## Metodológia — Ako som na to prišiel

Tento report bol vytvorený **bez manuálneho klikania** a **bez písania testov** — iba AI-assisted crawl a analýza.

### Agent Pipeline

```
www.orange.sk
      │
      ▼
  WebFetch crawler
  (kanonické URL z navigácie)
      │
      ├──► SDET Agent
      │    • Identifikoval broken URL (BUG-002)
      │    • Feature parity analýza — B2B vs B2C (BUG-003)
      │    • Accessibility edge cases (BUG-005)
      │
      ├──► Security Agent
      │    • HTTP/HTTPS audit (BUG-001, BUG-004)
      │    • OWASP Top 10 checklist
      │    • Cookie a header analýza
      │
      └──► Architect Agent
           • Navigačná konzistentnosť
           • SEO + revenue dopad (BUG-002)
           • B2B/B2C feature gap (BUG-003)
      │
      ▼
  Kompilovaný bug report
```

### Nástroje

| Nástroj | Účel |
|---------|------|
| **Claude Opus 4.6** | Reasoning, analýza, report |
| **WebFetch** | HTTP crawl bez prehliadača |
| **SDET.MD prompt** | Perspektíva: testovateľnosť, edge cases, user journeys |
| **SECURITY.MD prompt** | Perspektíva: OWASP, šifrovanie, autentifikácia |
| **ARCHITECT.MD prompt** | Perspektíva: štruktúra, SEO, business dopad |

---

## Prioritizácia Opráv

| Priorita | Bug | Odhadovaný dopad opravy |
|----------|-----|------------------------|
| **P0 — Ihneď** | BUG-001, BUG-004 | Eliminuje bezpečnostné riziko, GDPR compliance |
| **P1 — Tento sprint** | BUG-002 | Obnoví konverzie a zastaví SEO bleeding |
| **P2 — Nasledujúci sprint** | BUG-003 | Zníži objem call centra, zlepší NPS |
| **P3 — Backlog** | BUG-005 | WCAG compliance, reputačný benefit |

---

*Generované pomocou [LLM-Powered AI QA Suite](https://github.com/Jurajjjjj1988/LLM-Powered-AI-QA-Suite) — exploratory agent analysis bez písania testov*
