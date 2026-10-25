# Supabase email + 8-digit OTP setup

TrustVault creates accounts with Supabase Auth `POST /auth/v1/signup`, which
sends the **Confirm signup** email. The 8-digit code in that email is the
`{{ .Token }}` variable. If the template does not include `{{ .Token }}`, the
user receives a link only and the verification screen has nothing to accept.

> Editing the **Magic Link** template is not enough. Password registration uses
> **Confirm signup**. Edit that template.

## 1. Confirm the OTP length is 8

Dashboard → **Authentication** → **Providers** → **Email**:

- **Email OTP length** must be `8` (the API rejects any other length).
- **Email OTP expiration** should be at least `3600` seconds.

## 2. Put the code and the link in the Confirm signup template

Dashboard → **Authentication** → **Emails** → **Confirm signup**.
Replace the body with:

```html
<h2>Verify your TrustVault account</h2>
<p>Your verification code is:</p>
<p style="font-size: 32px; font-weight: 700; letter-spacing: 8px; margin: 16px 0;">
  {{ .Token }}
</p>
<p>Enter this 8-digit code on the verification page. It expires in 1 hour.</p>
<p>Or verify instantly by clicking this link:</p>
<p><a href="{{ .ConfirmationURL }}">Verify my email address</a></p>
<p>If you did not create a TrustVault account, you can ignore this email.</p>
```

`{{ .ConfirmationURL }}` sends the user to the configured redirect
(`http://localhost:5173/login` in development). The app detects the session in
the URL and lands on `/dashboard` automatically.

Do the same for **Magic Link** and **Reset password** if you use those flows;
each template needs `{{ .Token }}` for the code to appear.

## 3. Configure custom SMTP (required for reliable delivery)

Supabase's built-in mailer is a testing service with a very low hourly limit
and poor deliverability. Once the limit is hit, `/auth/v1/resend` still returns
`200 {}` but **no email is sent** — which looks exactly like "the OTP never
arrives".

Dashboard → **Project Settings** → **Authentication** → **SMTP Settings**:
enable custom SMTP and enter the host, port, username, password, sender email,
and sender name from a provider such as Resend, Brevo, SendGrid, Mailgun, or
Postmark.

## 4. Allow the redirect URL

Dashboard → **Authentication** → **URL Configuration** → **Redirect URLs**:
add every origin the app runs on, for example:

```
http://localhost:5173/login
https://your-production-domain/login
```

## 5. Verify the whole flow

1. Register with a fresh address.
2. The response is `200 {"account_created": true, "requires_email_confirmation": true}`.
3. The email contains **both** an 8-digit code and a verification link.
4. Enter the code on `/verify-account` → the app calls
   `/api/v1/auth/supabase/verify-signup`, creates the local profile, and routes
   to `/dashboard`.
5. Or click the link → Supabase redirects to `/login` with a session → the app
   calls `/api/v1/auth/session`, links the profile, and routes to `/dashboard`.

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| Email has a link but no code | Template missing `{{ .Token }}` | Step 2 |
| No email at all, API returns 200 | Built-in mailer rate limit / spam filtering | Step 3 |
| Code is 6 digits but the form wants 8 | Email OTP length is not 8 | Step 1 |
| `400 already registered` for a new user | Local row without a Supabase identity | Fixed: registration now clears the stale link and recreates the provider account |
| `503` on register | Supabase lookup unreachable | Retry; the app fails closed instead of guessing |
