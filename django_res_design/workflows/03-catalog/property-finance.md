# Property Finance

The `VillaFinance` god-object carries five distinct concerns: commission, tax, bank account, payment schedule, and security deposit policy. All five are multiplexed through **one** stored procedure (`sp_crud_VillaFinance`) with **33 parameters**. The Django redesign in `../03-finance-config.md` splits these into five OneToOne-attached models.

## Configure property finance

**ID:** `CATALOG.PROPERTY_FINANCE.UPDATE`
**Trigger:** Save on the Finance tab of `/property-detail/{PropertyId}` (`PropertyFinance.razor`).
**Actor:** Finance manager.
**Legacy locus:** `PropertyService2.cs:86-218` (`GetUpdatePropertyFinanceDetails`); SP `sp_crud_VillaFinance`.

### Inputs (organised by concern)

**Commission:**
- `CommissionTypeId` (FK `CalculationType` — % vs fixed)
- `CommissionAmount` (decimal)
- `CommissionNote`
- `IsDefaultCommission` (bool — use system default)

**Tax:**
- `TaxNumber` (VAT ID)
- `TaxExempt` (bool)
- `TaxPercentage` (decimal)
- `IsDefaultTax` (bool)
- `IsManualUpdate` (bool — flag for manual override)

**Bank account:**
- `BankAccAccountname`, `BankAccAccountnumber`, `BankAccAccountSortCode`, `BankAccAccountIBAN`, `BankAccAccountBIC`
- `BankAccAddres1`, `BankAccAddres2`, `BankAccAddres3`, `BankAccTown`, `BankAccCounty`, `BankAccPostCode`, `BankAccCountry`
- `IsDefaultSettingBank` (bool)

**Payment schedule (deposit + interim + balance):**
- `PaymentScheduleIsDepositRequired`, `PaymentScheduleDepositTypeId`, `PaymentScheduleDepositAmount`
- `PaymentScheduleIsInterimRequired`, `PaymentScheduleInterimTypeId`, `PaymentScheduleInterimAmount`
- `PaymentScheduleDaysInterimDueBeforeArrival`, `PaymentScheduleDaysBalanceDueBeforeArrival`
- `IsDefaultPaysched`

**Security deposit:**
- `SecurityDepositIsRequired`
- `SecurityDepositPaymentMethod` (int — 10=CC pre-auth, 20=BT)
- `SecurityDepositAmountTypeId` (FK `CalculationType` — % vs fixed)
- `SecurityDepositAmount`
- `SecurityDepositCalculateFromId` (FK `CalculationType` — basis: rental amount, balance, etc.)
- `SecurityDepositDaysDueBeforeArrival`, `SecurityDepositDaysDefundedAfterDeparture` `[TYPO]` — the real column name on `VillaMaster` / `VillaConfigPropertyDefault` (`live-db-24-apr.sql:61420`) is **`SecurityDepositDaysDefundedAfterDeparture`** (should be `Refunded`). `PropertyService2.cs:200` reads the typo column from the row and assigns it to a C# property called `SecurityDepositDaysRefundedAfterDeparture` — so the typo is the source of truth and the "correct" name only exists in the .NET model. The Django port must read from the typo column and rename on migration; do **not** assume the clean name maps to a real column without an explicit rename.
- `IsDefaultSecDep`

### Process
1. Build 33-parameter list.
2. Execute `sp_crud_VillaFinance` with `@Action` ∈ {`SELECT`, `INSERT`, `UPDATE`}.
3. **Post-load defaulting**: when `Action=SELECT`, for each `IsDefault*` flag set to `true`, replace the returned value with the corresponding `_defaultProperty` field (`PropertyService2.cs:150-218`). Example: if `IsDefaultTax=true`, the returned `TaxPercentage` is overwritten with `_defaultProperty.TaxPercentage` from `VillaConfigPropertyDefault`.

### Outputs / side effects
- **DB write:** `VillaFinance` row (INSERT or UPDATE).
- Response object carries values with defaults already resolved.
- **No outbound sync** — finance config is consumed locally by the pricing engine and booking workflows.

### Data transformations for storage
- Decimal precision preserved; no implicit currency context (currency lives on `VillaSettings.SettingCurrencyId`).
- `IsManualUpdate` is a flag that prevents an automated overwrite (e.g., bulk import) from clobbering a hand-tuned value.

### Failure modes
- `VillaId <= 0` → SP fails.
- `CommissionAmount <= 0` triggers the default fallback path rather than rejecting (`PropertyService2.cs:156-157`) — the property silently uses the system default.

### Open questions
- The `IsDefault*` + value pattern is verbose and error-prone. The Django redesign uses **nullable column + `effective_*()` resolver**, which the docs in `../03-finance-config.md` define precisely.
- Decompose into `PropertyCommission`, `PropertyTax`, `PropertyBankAccount`, `PropertyPaymentSchedule`, `PropertySecurityDepositPolicy` — each OneToOne with `Property` and each with its own service.
- Bank account details on the property row is unusual — bank accounts probably belong to the **owner contact** in a normalised model.
