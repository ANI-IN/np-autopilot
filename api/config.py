"""GET /api/config — the public values a browser needs to start a login.

All three are PUBLIC by design and none is a secret:

  SUPABASE_URL             appears in every request the browser makes
  SUPABASE_ANON_KEY        the key a browser holds; grants nothing on its own,
                           because every table is default-deny and np_role()
                           returns 'none' without a profile
  GOOGLE_OAUTH_CLIENT_ID   published in the OAuth redirect anyway

They are served rather than baked into the HTML so that the same page works
against a preview deployment without an edit, and so a rotated key does not
need a rebuild. `SUPABASE_SERVICE_ROLE_KEY` is never read in this file, and
`tests/test_no_service_key_in_client.py` asserts it appears in no file the
browser can fetch.
"""
import os

# Vercel discovers Python functions at /api in the project root, so this
# file sits one level above web/. The shared modules stay in web/lib.

def payload() -> dict:
    """The three public values, and a named error when one is missing.

    A blank client id would otherwise surface as Google's generic "invalid
    request" with nothing pointing back here.
    """
    body = {
        "supabase_url": os.environ.get("SUPABASE_URL", ""),
        "supabase_anon_key": os.environ.get("SUPABASE_ANON_KEY", ""),
        "google_client_id": os.environ.get("GOOGLE_OAUTH_CLIENT_ID", ""),
        "allowed_hd": os.environ.get("NP_ALLOWED_HD", "interviewkickstart.com"),
    }
    missing = [k for k, v in body.items() if not v]
    if missing:
        body["error"] = f"not configured: {', '.join(missing)}"
    return body
