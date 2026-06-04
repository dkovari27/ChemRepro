import httpx

from app.config import settings


def get_auth_url(state: str) -> str:
    """Build the ORCID OAuth2 authorisation URL."""
    params = (
        f"client_id={settings.ORCID_CLIENT_ID}"
        f"&response_type=code"
        f"&scope=/authenticate"
        f"&redirect_uri={settings.ORCID_REDIRECT_URI}"
        f"&state={state}"
    )
    return f"{settings.orcid_base_url}/oauth/authorize?{params}"


async def exchange_code_for_token(code: str) -> dict | None:
    """Exchange an auth code for an ORCID access token. Returns token payload."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{settings.orcid_base_url}/oauth/token",
            data={
                "client_id": settings.ORCID_CLIENT_ID,
                "client_secret": settings.ORCID_CLIENT_SECRET,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.ORCID_REDIRECT_URI,
            },
            headers={"Accept": "application/json"},
        )
    if resp.status_code != 200:
        return None
    return resp.json()


async def fetch_orcid_name(orcid_id: str, access_token: str) -> str | None:
    """Fetch the user's display name from the ORCID API."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{settings.orcid_api_url}/{orcid_id}/person",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            },
        )
    if resp.status_code != 200:
        return None
    data = resp.json()
    name_data = data.get("name") or {}
    given = (name_data.get("given-names") or {}).get("value", "")
    family = (name_data.get("family-name") or {}).get("value", "")
    full = f"{given} {family}".strip()
    return full or None
