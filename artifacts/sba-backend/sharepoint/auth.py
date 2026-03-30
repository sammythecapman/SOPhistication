"""
SharePoint authentication using MSAL (Microsoft Authentication Library).

Setup Instructions:
1. Register an app in Azure AD (portal.azure.com → Azure Active Directory → App registrations)
2. Add permissions: Sites.ReadWrite.All, Files.ReadWrite.All
3. Create a client secret
4. Set environment variables:
   - SHAREPOINT_CLIENT_ID
   - SHAREPOINT_CLIENT_SECRET
   - SHAREPOINT_TENANT_ID
   - SHAREPOINT_SITE_URL
"""

import os
from typing import Optional


class SharePointAuth:
    """Handles MSAL authentication for SharePoint Online."""

    def __init__(self):
        self.client_id = os.environ.get("SHAREPOINT_CLIENT_ID")
        self.client_secret = os.environ.get("SHAREPOINT_CLIENT_SECRET")
        self.tenant_id = os.environ.get("SHAREPOINT_TENANT_ID")
        self.site_url = os.environ.get("SHAREPOINT_SITE_URL")
        self._token_cache = None

    @property
    def is_configured(self) -> bool:
        """Check if all required SharePoint credentials are configured."""
        return all([self.client_id, self.client_secret, self.tenant_id, self.site_url])

    def get_access_token(self) -> Optional[str]:
        """
        Get an access token for Microsoft Graph API using client credentials flow.
        Returns None if SharePoint is not configured.
        """
        if not self.is_configured:
            return None

        try:
            import msal

            authority = f"https://login.microsoftonline.com/{self.tenant_id}"
            scope = ["https://graph.microsoft.com/.default"]

            app = msal.ConfidentialClientApplication(
                self.client_id,
                authority=authority,
                client_credential=self.client_secret,
            )

            result = app.acquire_token_silent(scope, account=None)
            if not result:
                result = app.acquire_token_for_client(scopes=scope)

            if "access_token" in result:
                return result["access_token"]
            else:
                raise RuntimeError(f"Token acquisition failed: {result.get('error_description', 'Unknown error')}")

        except ImportError:
            raise RuntimeError("msal package is not installed")

    def get_headers(self) -> dict:
        """Get authorization headers for Graph API calls."""
        token = self.get_access_token()
        if not token:
            raise RuntimeError("SharePoint credentials are not configured")
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
