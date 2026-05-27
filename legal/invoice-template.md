# Invoice template — dcm-anon-vault

Use for: any Customer where Stripe-automatic invoicing is not used (Enterprise tier, manual invoice).

---

```
FACTURA / INVOICE Nº [YYYY-NNNN]

Date / Fecha:                    [YYYY-MM-DD]
Due date / Vencimiento:           [YYYY-MM-DD]  (Net 15 days unless agreed otherwise)

------------------------------------------------------------------
SELLER / VENDEDOR

César Pereiro García (autónomo / indiv. professional)
NIF: [TO PROVIDE]
Address: [SPANISH ADDRESS]
Email: plusultra.dev@proton.me

------------------------------------------------------------------
BUYER / COMPRADOR

[Customer legal name]
[Address line 1]
[Address line 2 / city]
[Country]
VATIN: [Customer VAT number, e.g. ES-A12345678 or DE123456789]
Contact: [billing contact email]

------------------------------------------------------------------
SERVICE / SERVICIO

dcm-anon-vault — [Tier name] subscription
Period: [YYYY-MM-DD] to [YYYY-MM-DD]
Tenant id: [tenant-uuid]

Quantity:  1
Unit price (EUR, net): [amount]
------------------------------------------------------------------

Subtotal:              EUR [amount]

VAT decision (choose one and delete others):

(a) EU B2B reverse-charge under Art. 196 Directive 2006/112/EC.
    Buyer VATIN [Customer VATIN] verified via VIES on [date].
    "VAT reverse charge — Art. 196 Dir. 2006/112/EC".
    VAT: EUR 0,00. Buyer accounts for VAT in its jurisdiction.

(b) Non-EU buyer. Service outside the scope of EU VAT.
    "Service provided outside EU VAT scope under Art. 44 Dir. 2006/112/EC".
    VAT: EUR 0,00.

(c) Spanish-resident buyer. (NOT YET SUPPORTED — defer until autónomo registration.)

------------------------------------------------------------------

TOTAL DUE:             EUR [amount]

Payment instructions:
  - Bank transfer (EUR): IBAN [TO PROVIDE], BIC [TO PROVIDE].
  - Stripe Payment Link or SEPA bank transfer (see pricing.md, Payment section).
  - Reference / Concepto: invoice-[YYYY-NNNN]

Late payment: statutory commercial interest per Spanish Ley 3/2004 transposing Dir. 2011/7/EU.

Disputes: notify within 7 days of receipt.

This invoice is governed by the dcm-anon-vault Terms of Service (legal/tos.md), the executed Order Form, and the Data Processing Agreement where applicable.
```

## VAT decision tree (for the operator)

1. Customer Spanish-resident? → tier (c) above. Currently NOT SUPPORTED until principal completes autónomo registration. Refuse the engagement or wait.
2. Customer EU-resident, valid VATIN (verify via [VIES](https://ec.europa.eu/taxation_customs/vies/))? → tier (a) reverse-charge.
3. Customer EU-resident, no VATIN or B2C? → currently NOT SUPPORTED (would require VAT-OSS registration). Refuse or defer.
4. Customer non-EU? → tier (b) out-of-scope.

## Numbering convention

`YYYY-NNNN` where NNNN is a monotonically increasing counter restarted each calendar year. Do not skip numbers. Spanish tax law requires sequential invoicing.

## Retention

Invoices retained 6 years per Spanish tax law (Ley General Tributaria).
