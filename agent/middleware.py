from django.utils.deprecation import MiddlewareMixin
from django.conf import settings
import re

class SecurityHeadersMiddleware(MiddlewareMixin):
    def process_response(self, request, response):
        # Content Security Policy
        csp = [
            "default-src 'self'",
            f"connect-src 'self' {settings.KONNECT_CONFIG['BASE_URL']}",
            "script-src 'self' 'unsafe-inline' https://cdn.konnect.network",
            "style-src 'self' 'unsafe-inline'",
            f"img-src 'self' data: https://*.mytek.tn https://*.tunisianet.com",
            f"frame-src 'self' {settings.KONNECT_CONFIG['BASE_URL']}",
            "form-action 'self'"
        ]

        response['Content-Security-Policy'] = "; ".join(csp)
        response['X-Content-Type-Options'] = 'nosniff'
        response['X-Frame-Options'] = 'DENY'
        response['Referrer-Policy'] = 'strict-origin-when-cross-origin'

        # Tunisian phone number masking
        if hasattr(response, 'content'):
            content = response.content.decode()
            tunisian_phone_regex = r'(\+216\s?\d{2}\s?\d{3}\s?\d{3})'
            content = re.sub(
                tunisian_phone_regex,
                lambda m: m.group(1)[:6] + 'XXX' + m.group(1)[-3:],
                content
            )
            response.content = content.encode()

        return response
