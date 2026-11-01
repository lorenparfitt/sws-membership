# API

Every route of the JSON API, generated from the routes themselves by
`uv run doit api_doc`. Edit the route docstrings and models, not this file;
a test fails when the two disagree. The interactive version, with every
field and a try-it button, is served at `/api/docs`, and the OpenAPI
document at `/api/openapi.json`.

## Conventions

- **Who** is the role the route requires. `none` is open; `member` is any
  signed-in member; `staff` is the staff or admin role; `admin` is the admin
  role. No session answers 401, a session without the role 403.
- Sessions are cookies set by the sign-in routes. Every write (POST, PUT,
  DELETE) must echo the `csrftoken` cookie in an `X-CSRFToken` header; the
  processor webhook and the sign-in routes are exempt.
- Bodies and responses are JSON unless the response says bytes or text.
  Money is integer cents in CAD. Dates are ISO 8601.
- A request that is well formed but not allowed answers 409. When the cause
  is eligibility (a product the member cannot buy), the body is
  `{"detail": {"refused": {"<product or order>": ["<reason>", ...]}}}`;
  otherwise `detail` is a sentence. 404 is both missing and not yours.
- Routes marked *development only* exist only when the fake payment
  processor is configured.

## admin

| Method | Path | Who | Does | Request | Response |
|---|---|---|---|---|---|
| GET | `/api/admin/catalog/options` | admin | The closed lists the catalog editor offers: entitlement kinds, and rule kinds with their parameters. | - | 200 JSON object |
| GET | `/api/admin/catalog/products` | admin | Every product with its prices, grants and rules, optionally for one season. | query season_year: int or None | 200 list[AdminProductView] |
| POST | `/api/admin/catalog/products` | admin | Create a product. | body ProductBody | 201 AdminProductView |
| PUT | `/api/admin/catalog/products/{product_id}` | admin | Change a product's name, description, season, sort order or active flag. | body ProductBody | 200 AdminProductView |
| POST | `/api/admin/catalog/products/{product_id}/grants` | admin | Add an entitlement the product confers. | body GrantBody | 201 AdminProductView |
| DELETE | `/api/admin/catalog/products/{product_id}/grants/{grant_id}` | admin | Remove a grant. | - | 200 AdminProductView |
| POST | `/api/admin/catalog/products/{product_id}/prices` | admin | Add a price window to a product. | body PriceBody | 201 AdminProductView |
| DELETE | `/api/admin/catalog/products/{product_id}/prices/{price_id}` | admin | Remove a price that no order has used. | - | 200 AdminProductView |
| POST | `/api/admin/catalog/products/{product_id}/rules` | admin | Add an eligibility rule to a product. | body RuleBody | 201 AdminProductView |
| DELETE | `/api/admin/catalog/products/{product_id}/rules/{rule_id}` | admin | Remove a rule. | - | 200 AdminProductView |
| POST | `/api/admin/catalog/rollover` | admin | Copy one season's catalog to the next. | body RolloverBody | 201 list[AdminProductView] |
| GET | `/api/admin/reports` | admin | The reports that exist and the parameters each takes. | - | 200 list[ReportView] |
| POST | `/api/admin/reports/{name}/csv` | admin | Run a report and return it as CSV. | body ReportRun | 200 bytes or text |
| POST | `/api/admin/reports/{name}/run` | admin | Run a report and return its table. | body ReportRun | 200 ReportOutput |
| GET | `/api/admin/waiver/history` | admin | Every published waiver version and every reset. | - | 200 WaiverHistory |

## auth

| Method | Path | Who | Does | Request | Response |
|---|---|---|---|---|---|
| GET | `/api/auth/me` | member | Who is signed in: name, member number, roles. | - | 200 MemberView |
| POST | `/api/auth/password` | none | Sign in with email and password. | body PasswordSignIn | 200 MemberView |
| POST | `/api/auth/redeem` | none | Sign in with an emailed link token; the token is spent. | body Redemption | 200 MemberView |
| POST | `/api/auth/request-link` | none | Email a single-use sign-in link to the address, whether or not a member has it. | body LinkRequest | 202 JSON object |
| POST | `/api/auth/set-password` | member | Set or change the signed-in member's password. | body NewPassword | 204 empty |
| POST | `/api/auth/sign-out` | none | End the session. | - | 204 empty |

## cards

| Method | Path | Who | Does | Request | Response |
|---|---|---|---|---|---|
| GET | `/api/me/card.pdf` | member | The signed-in member's card as a PDF. | - | 200 bytes or text |
| POST | `/api/staff/cards/print` | staff | A PDF for the given members, and a print record for each. | body BatchBody | 200 bytes or text |

## catalog

| Method | Path | Who | Does | Request | Response |
|---|---|---|---|---|---|
| GET | `/api/catalog` | member | Products on sale to the signed-in member today, with prices and why any is locked; basket ids count as held. | query basket: list[int] | 200 list[ProductView] |

## entitlements

| Method | Path | Who | Does | Request | Response |
|---|---|---|---|---|---|
| GET | `/api/entitlements` | member | The passes the signed-in member holds. | - | 200 list[EntitlementView] |

## kiosk

| Method | Path | Who | Does | Request | Response |
|---|---|---|---|---|---|
| POST | `/api/staff/kiosk/check-in` | staff | Admit a member at a station on their best pass; one admission per station per day. | body CheckInBody | 200 CheckInResult |
| GET | `/api/staff/kiosk/lookup` | staff | Find members by scanned number, email or name, with passes and waiver status. | query q: str | 200 list[MemberGateView] |
| GET | `/api/staff/kiosk/today` | staff | Check-ins so far today, per station. | - | 200 JSON object |

## members

| Method | Path | Who | Does | Request | Response |
|---|---|---|---|---|---|
| GET | `/api/me/photo` | member | The signed-in member's stored photo. | - | 200 bytes or text |
| POST | `/api/me/photo` | member | Upload the signed-in member's face photo for the card. | file photo | 200 ProfileView |
| GET | `/api/me/profile` | member | The signed-in member's profile and what it is still missing. | - | 200 ProfileView |
| PUT | `/api/me/profile` | member | Update the signed-in member's contact details, address and sports. | body ProfileBody | 200 ProfileView |
| GET | `/api/sports` | none | The closed list of sports a member can practise. | - | 200 JSON list |
| GET | `/api/staff/members/{member_id}/photo` | staff | A member's stored photo, for the kiosk. | - | 200 bytes or text |
| POST | `/api/staff/members/{member_id}/photo` | staff | Take or replace a member's photo at the counter. | file photo | 200 ProfileView |

## orders

| Method | Path | Who | Does | Request | Response |
|---|---|---|---|---|---|
| POST | `/api/admin/orders/{order_id}/refund` | admin | Give a paid order back in full and withdraw the passes it bought. | body RefundBody | 200 OrderView |
| GET | `/api/orders` | member | The signed-in member's orders, newest first. | - | 200 list[OrderView] |
| POST | `/api/orders` | member | Place a card order for the basket and open the processor's checkout. | body NewOrder | 201 OrderView |
| POST | `/api/orders/quote` | member | Price a basket as a whole, before any order exists. | body NewOrder | 200 QuoteView |
| GET | `/api/orders/{order_id}` | member | One of the signed-in member's orders. | - | 200 OrderView |
| POST | `/api/orders/{order_id}/cancel` | member | Withdraw an unpaid card order. | - | 200 OrderView |
| POST | `/api/orders/{order_id}/checkout` | member | A fresh processor session for an unpaid card order. | - | 200 OrderView |
| GET | `/api/orders/{order_id}/receipt` | member | The plain-text receipt of a paid order. | - | 200 bytes or text |
| POST | `/api/payments/notification` | none | The processor's webhook. Form encoded; answers OK once stored. Not in the OpenAPI document. | - | 200 bytes or text |
| POST | `/api/staff/orders` | staff | Ring up any member. Cash and free pay at once; card opens the processor form. | body StaffOrder | 201 OrderView |
| POST | `/api/staff/orders/quote` | staff | Price a basket for any member at the till. | body StaffQuote | 200 QuoteView |
| GET | `/api/staff/orders/{order_id}` | staff | Any member's order. | - | 200 OrderView |
| POST | `/api/staff/orders/{order_id}/cancel` | staff | Withdraw any unpaid card order. | - | 200 OrderView |
| POST | `/api/staff/orders/{order_id}/checkout` | staff | A fresh processor session for any unpaid card order. | - | 200 OrderView |
| GET | `/api/staff/orders/{order_id}/receipt` | staff | The plain-text receipt of any paid order. | - | 200 bytes or text |

## payments-fake

| Method | Path | Who | Does | Request | Response |
|---|---|---|---|---|---|
| POST | `/api/payments/fake/approve/{order_id}` | member (development only) | Development only: approve a card order as the fake processor would. | - | 200 JSON object |

## staff-members

| Method | Path | Who | Does | Request | Response |
|---|---|---|---|---|---|
| GET | `/api/staff/members/{member_id}` | staff | Everything the counter needs about one member: profile, passes, orders, what they can buy. | - | 200 MemberDetail |
| PUT | `/api/staff/members/{member_id}/profile` | staff | Staff may correct anything, including the birth date and email. | body StaffProfileBody | 200 MemberDetail |
| PUT | `/api/staff/members/{member_id}/roles` | admin | Set a member's roles (staff, admin). | body RolesBody | 200 MemberDetail |

## waivers

| Method | Path | Who | Does | Request | Response |
|---|---|---|---|---|---|
| POST | `/api/admin/waiver/publish` | admin | Publish a new waiver version; everyone must sign again. | body PublishBody | 201 JSON object |
| POST | `/api/admin/waiver/reset` | admin | Force everyone to sign the current waiver again. | body ResetBody | 201 JSON object |
| GET | `/api/waiver` | member | The current waiver text and whether the signed-in member has signed it. | - | 200 WaiverView |
| POST | `/api/waiver/sign` | member | Sign the current waiver with a drawn signature, plus a guardian's for a minor. | body SignatureBody | 201 WaiverView |

## Shapes

Request and response bodies. A trailing `?` marks a field the sender may omit.

- **AdminProductView**: id: integer, name: string, description: string, season_year: integer, sort_order: integer, active: boolean, prices: list of PriceView, grants: list of GrantView, rules: list of RuleView
- **BatchBody**: member_ids: list of integer
- **CheckInBody**: member_id: integer, station: Station
- **CheckInResult**: admitted: boolean, new_today: boolean, message: string, member: MemberGateView
- **CheckInView**: station: string, checked_in_at: date-time, product_name: string
- **CheckoutView**: processor: string, session_token: string, parameters: object of string
- **EntitlementKind**: `membership` | `season_access` | `day_visits` | `shuttle_access`
- **EntitlementView**: id: integer, kind: string, product_name: string, valid_from: date, valid_to: date, visits_remaining: integer or null, active: boolean
- **GrantBody**: kind: EntitlementKind, valid_from: date, valid_to: date, visit_count?: integer or null
- **GrantView**: id: integer, kind: string, valid_from: date, valid_to: date, visit_count: integer or null
- **LineView**: product_name: string, amount_cents: integer
- **LinkRequest**: email: email
- **MemberDetail**: id: integer, member_number: integer, roles: list of string, has_photo: boolean, profile: ProfileView, waiver_current: boolean, waiver_signed_at: date-time or null, passes: list of PassView, today: list of CheckInView, orders: list of OrderView, catalog: list of ProductView
- **MemberGateView**: id: integer, member_number: integer, first_name: string, last_name: string, email: string, date_of_birth: date or null, photo_key: string or null, waiver_current: boolean, passes: list of PassView, today: list of CheckInView
- **MemberRole**: `staff` | `admin`
- **MemberView**: id: integer, member_number: integer, first_name: string, last_name: string, email: string, roles: list of string, has_password: boolean
- **NewOrder**: product_ids: list of integer
- **NewPassword**: password: string
- **OrderView**: id: integer, status: string, payment_method: string, total_cents: integer, currency: string, created_at: date-time, paid_at: date-time or null, lines: list of LineView, refund?: RefundView or null, checkout?: CheckoutView or null
- **ParameterView**: name: string, label: string, kind: string, default: any
- **PassView**: id: integer, kind: string, product_name: string, valid_from: date, valid_to: date, visits_remaining: integer or null, active: boolean
- **PasswordSignIn**: email: email, password: string
- **PaymentMethod**: `card` | `cash` | `free`
- **PriceBody**: label?: string, amount_cents: integer, starts_at: date, ends_at?: date or null, members_only?: boolean
- **PriceView**: id: integer, label: string, amount_cents: integer, starts_at: date, ends_at: date or null, members_only: boolean
- **ProductBody**: name: string, description?: string, season_year: integer, sort_order?: integer, active?: boolean
- **ProductView**: id: integer, name: string, description: string, season_year: integer, grants: list of string, price: PriceView or null, purchasable: boolean, locked_because: list of string
- **ProfileBody**: first_name: string, last_name: string, phone?: string or null, date_of_birth?: date or null, address_line_1?: string or null, address_line_2?: string or null, city?: string or null, province?: string or null, postal_code?: string or null, sports?: list of Sport
- **ProfileView**: first_name: string, last_name: string, email: string, phone: string or null, date_of_birth: date or null, address_line_1: string or null, address_line_2: string or null, city: string or null, province: string or null, postal_code: string or null, sports: list of string, has_photo: boolean, missing: list of string
- **PublishBody**: title: string, body_text: string
- **QuoteLineView**: product_name: string, amount_cents: integer, product_id: integer
- **QuoteView**: lines: list of QuoteLineView, refused: object of list of string, total_cents: integer, currency: string
- **Redemption**: token: string
- **RefundBody**: reason: string
- **RefundView**: amount_cents: integer, reason: string, refunded_at: date-time, refunded_by: string
- **ReportOutput**: title: string, columns: list of string, rows: list of list of any
- **ReportRun**: parameters?: object
- **ReportView**: name: string, title: string, description: string, parameters: list of ParameterView
- **ResetBody**: reason: string
- **ResetView**: reset_at: date-time, reason: string
- **RolesBody**: roles: list of MemberRole
- **RolloverBody**: from_year: integer, to_year: integer
- **RuleBody**: kind: RuleKind, parameters?: object, failure_message: string
- **RuleKind**: `requires_active_entitlement` | `requires_current_waiver` | `profile_complete` | `age_at_least` | `age_at_most` | `one_per_member_per_season`
- **RuleView**: id: integer, kind: string, parameters: object, failure_message: string
- **SignatureBody**: template_id: integer, signer_name: string, signature_png: string, guardian_name?: string or null, guardian_signature_png?: string or null
- **Sport**: `kite_twin_tip` | `kite_foil` | `kite_surfboard` | `wing` | `windsurf` | `other`
- **StaffOrder**: product_ids: list of integer, member_id: integer, payment_method: PaymentMethod
- **StaffProfileBody**: first_name: string, last_name: string, email: email, phone?: string or null, date_of_birth?: date or null, address_line_1?: string or null, address_line_2?: string or null, city?: string or null, province?: string or null, postal_code?: string or null, sports?: list of Sport
- **StaffQuote**: product_ids: list of integer, member_id: integer
- **Station**: `spit` | `shuttle`
- **TemplateView**: id: integer, version: integer, title: string, body_text: string, published_at: date-time
- **WaiverHistory**: templates: list of TemplateView, resets: list of ResetView
- **WaiverView**: template_id: integer or null, version: integer or null, title: string or null, body_text: string or null, document_hash: string or null, signed: boolean, signed_at: date-time or null, needs_guardian: boolean
