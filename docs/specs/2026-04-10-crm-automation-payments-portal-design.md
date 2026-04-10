# Garcia Folklorico Studio - CRM Automation, Payments & Parent Portal

**Date:** 2026-04-10
**Status:** Approved
**Client:** Garcia Folklorico Studio (Oxnard, CA)
**Built by:** WestCoast Automation Solutions

## Overview

Extend the Garcia Folklorico CRM and booking system with:
1. Automatic CRM sync from backend events (pipeline progression, email logging)
2. Stripe payment integration (optional, dormant until configured)
3. Production-grade parent portal with full auth system
4. Daily digest emails and block transition automation

## 1. CRM Auto-Sync

### Event-Driven Architecture

Backend emits JSON event files to `pipeline_events/` directory when actions occur. A cron job (`crm_events.py`, every 5 min) processes events and writes to the Google Sheet.

**Events emitted:**

| Event | Trigger | CRM Action |
|-------|---------|------------|
| `registration_created` | Parent registers child | Add row to Student Pipeline (stage: Enrolled), add row to Revenue & Payments (Unpaid) |
| `registration_waitlisted` | Class full at registration | Add row to Student Pipeline (stage: Waitlisted) |
| `registration_cancelled` | Parent or admin cancels | Update Pipeline row to Lost, update Revenue row to Waived |
| `waitlist_promoted` | Spot opens, next person promoted | Update Pipeline row from Waitlisted to Enrolled |
| `rental_booked` | Studio rental confirmed | Add row to Revenue & Payments (type: Rental, Unpaid) |
| `payment_received` | Stripe webhook or manual | Update Revenue row to Paid with date and method |
| `email_sent` | Any system email sent | Add row to Communications Log with channel, direction, summary |

### Why Event Files

- Backend stays fast (no Sheets API latency on user requests)
- Events queue up if Sheets API is down
- Same pattern as Americal Patrol's `pipeline_events/`

### Email Auto-Logging

Every email the system sends (registration confirmation, waitlist notification, promotion, rental confirmation) automatically creates a Communications Log entry with:
- Contact name, child name
- Pipeline stage at time of contact
- Channel: Email
- Direction: Outbound
- Summary: auto-generated from email type
- Touch number: auto-incremented per contact

### Files

- `automation/crm_events/run_crm_events.py` - main event processor
- `automation/crm_events/sheets_writer.py` - Google Sheets write helpers (find row, update row, append row)
- Backend route files emit events via `shared_utils.publish_event()`

## 2. Payment Integration (Stripe)

### Flow

**Registration (optional pay):**
1. Parent submits registration form
2. Confirmation screen shows two options:
   - "Pay Now" button -> Stripe Checkout -> redirect to success page
   - "Pay Later" note -> registration confirmed, Revenue row = Unpaid
3. If Stripe keys not configured, "Pay Now" button does not render

**Rental (same pattern):**
1. Rental booked and confirmed
2. Optional "Pay Now" for rental total
3. Same Stripe Checkout flow

**Stripe Webhook:**
- `POST /api/webhooks/stripe` receives payment confirmation
- Updates `payment_status` on Registration/RentalBooking
- Emits `payment_received` event -> Revenue & Payments tab updated to Paid

**Manual Payments:**
- Itzel marks payments directly in Revenue & Payments tab (Cash, Zelle, Venmo, Check)
- CRM is source of truth for manual payments

### Database Changes

Add to `Registration` model:
- `payment_status` (string: unpaid/paid/partial/refunded, default: unpaid)
- `payment_method` (string: card/cash/zelle/venmo/check, nullable)
- `stripe_session_id` (string, nullable)
- `parent_id` (FK to Parent, nullable for migration)

Add to `RentalBooking` model:
- `payment_status` (string: unpaid/paid/partial/refunded, default: unpaid)
- `payment_method` (string, nullable)
- `stripe_session_id` (string, nullable)
- `parent_id` (FK to Parent, nullable)

### Configuration

- `STRIPE_SECRET_KEY` in .env (empty = Stripe disabled)
- `STRIPE_WEBHOOK_SECRET` in .env (empty = webhooks disabled)
- `STRIPE_SUCCESS_URL` and `STRIPE_CANCEL_URL` for checkout redirects
- Block fees configured in `schedule_data.json` or CRM Settings tab

### Pricing Source

- Class tuition: per-class block fee stored in `schedule_data.json` (new field `block_fee` per class type)
- Rental: calculated from existing config ($75/hr standard, $60/hr at 4+ hrs)

## 3. Parent Portal

### Authentication System

**Account Creation:**
- During first class registration, parent creates account (email + password added to registration form)
- If email already exists, prompt to log in
- Password requirements: min 8 chars, at least one number and one letter
- Email verification: 6-digit code sent to email, must verify before account active
- Passwords hashed with bcrypt (cost factor 12)

**Login:**
- Email + password form at `/my-account`
- Rate-limited: 5 failed attempts -> 15-minute lockout per email
- JWT access token (15 min expiry) + refresh token (30 days, httpOnly cookie)
- "Remember me" extends refresh token to 90 days
- Session invalidation on password change

**Forgot Password:**
- Enter email -> time-limited reset link (1 hour, single-use)
- Reset page: new password + confirm
- Anti-enumeration: always shows "If an account exists, we sent a reset link"

**Change Password:**
- Requires current password + new password + confirm
- Invalidates all other sessions

**Change Email:**
- Requires current password
- Sends verification code to new email
- Old email stays active until new one verified

### Database Models

**Parent:**
- id (PK)
- email (unique, indexed)
- password_hash (string)
- name (string)
- phone (string)
- language (en/es)
- email_verified (bool, default false)
- created_at, updated_at (datetime)

**PasswordReset:**
- id (PK)
- parent_id (FK)
- token_hash (string)
- expires_at (datetime)
- used (bool, default false)

**RefreshToken:**
- id (PK)
- parent_id (FK)
- token_hash (string)
- expires_at (datetime)
- revoked (bool, default false)

### API Endpoints

**Auth:**
- `POST /api/auth/register` - create account + send verification code
- `POST /api/auth/verify-email` - submit 6-digit code
- `POST /api/auth/login` - email + password -> JWT + refresh cookie
- `POST /api/auth/refresh` - refresh token -> new JWT
- `POST /api/auth/logout` - revoke refresh token
- `POST /api/auth/forgot-password` - send reset link
- `POST /api/auth/reset-password` - token + new password

**Account:**
- `GET /api/account/dashboard` - all registrations + rentals + payments (requires JWT)
- `PUT /api/account/profile` - update name, phone, language
- `PUT /api/account/email` - change email (requires verification)
- `PUT /api/account/password` - change password (requires current)

### Frontend

- New page: `my-account.html`
- Vanilla HTML/CSS/JS (same stack as rest of site)
- Login form -> dashboard view (SPA-like with JS state management)
- Bilingual EN/ES with persistent toggle
- Responsive design matching existing site aesthetic
- Sections: My Children, My Rentals, Payment History, Profile Settings

### Security

- JWT signed with `JWT_SECRET` env var
- CSRF protection on state-changing endpoints
- HTTPS via Caddy (already configured)
- Password reset tokens: cryptographically random, single-use, stored hashed
- No sensitive data in JWT payload (just parent_id + expiry)
- Rate limiting on auth endpoints via in-memory counter

## 4. Daily Digest & Block Transitions

### Daily Digest Email (7 AM)

Pulls from database (not Sheet). Sent to Itzel at STUDIO_EMAIL.

**Contents:**
- New registrations in last 24 hours (child, class, parent contact)
- Cancellations in last 24 hours
- Class capacity snapshot (5 classes: enrolled / max / waitlisted)
- Classes at 80%+ capacity flagged
- Unpaid tuition count + total $ outstanding
- Today's rental bookings (time, renter, purpose)
- Waitlist movement (promotions, expirations)
- Action items needing attention

**Format:** Bilingual (Spanish primary, English below). Garcia brand styling (orange + lavender).

### Block Transition Automation (1 AM daily check)

**When block ends:**
1. All "registered" students moved to "Alumni" in Student Pipeline
2. Active Students tab clears (run_sync reflects DB state)
3. CRM event logged per transition
4. Digest flags: "Block [name] ended. X students completed."

**When new block seeded:**
1. Alumni from previous block flagged as "Re-enrollment" in Pipeline
2. System ready for new registrations

### Cron Schedule

| Job | Schedule | Script |
|-----|----------|--------|
| CRM event processor | `*/5 * * * *` | `crm_events/run_crm_events.py` |
| Sheets data sync | `*/15 * * * *` | `sheets_sync/run_sync.py` |
| Daily digest | `0 7 * * *` | `digest/run_digest.py` |
| Block transition | `0 1 * * *` | `block_transition/run_transition.py` |
| Class reminders | `0 16 * * *` | `reminders/run_reminders.py` |
| Waitlist follow-up | `0 */2 * * *` | `waitlist/run_waitlist.py` |
| Watchdog | `*/30 * * * *` | `watchdog/run_watchdog.py` |

## 5. Updated Registration Flow (End-to-End)

1. Parent visits `garciafolklorico.com/schedule`
2. Selects class, fills registration form (child info + parent info + email + password)
3. Backend creates `Parent` account (or links to existing) + `Registration`
4. Email verification code sent
5. If class has capacity: status = registered, confirmation email sent
6. If class full: status = waitlisted, waitlist email sent
7. CRM event emitted -> Student Pipeline row created, Revenue row created
8. Email auto-logged to Communications Log
9. Confirmation page shows: class details + "Pay Now" (if Stripe) + "Pay Later"
10. Parent verifies email via 6-digit code
11. Parent can log in at `/my-account` to see dashboard

## Architecture Diagram

```
Website (HTML/JS)
    |
    v
FastAPI Backend (api.garciafolklorico.com)
    |--- /api/auth/*        (JWT auth)
    |--- /api/classes/*     (registration + cancel)
    |--- /api/rentals/*     (booking)
    |--- /api/account/*     (parent dashboard)
    |--- /api/webhooks/*    (Stripe)
    |
    v
SQLite Database
    |--- Parent, Registration, RentalBooking
    |--- PasswordReset, RefreshToken
    |
    v
Event Files (pipeline_events/)
    |
    v
Cron Jobs (automation/)
    |--- crm_events    -> Google Sheets API
    |--- sheets_sync   -> Google Sheets API
    |--- digest        -> SMTP (Itzel's inbox)
    |--- block_transition -> DB updates + events
    |--- reminders     -> SMTP (parent reminders)
    |--- waitlist      -> SMTP (waitlist management)
    |--- watchdog      -> Health monitoring
```

## Dependencies

**New Python packages:**
- `pyjwt` - JWT token generation/validation
- `bcrypt` - password hashing
- `stripe` - Stripe API client (optional, graceful if not installed)

**Environment variables (new):**
- `JWT_SECRET` - signing key for JWT tokens
- `STRIPE_SECRET_KEY` - Stripe API key (empty = disabled)
- `STRIPE_WEBHOOK_SECRET` - Stripe webhook verification (empty = disabled)

## Deployment

Same standard method:
1. Push to `suaveshot/garcia-folklorico` on GitHub
2. Redeploy via Hostinger `VPS_createNewProjectV1`
3. New env vars added to the environment parameter
4. New cron jobs added to entrypoint.sh
