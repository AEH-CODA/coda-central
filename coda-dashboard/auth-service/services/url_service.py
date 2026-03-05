from fastapi import Request

def get_base_url(request: Request) -> str:
    """
    Extract the base URL from request, handling reverse proxies.
    
    Checks for X-Forwarded-Host and X-Forwarded-Proto headers (set by reverse proxies),
    falls back to Host header (direct connections).
    """
    forwarded_host = request.headers.get('x-forwarded-host')
    forwarded_proto = request.headers.get('x-forwarded-proto', 'http')
    host = forwarded_host or request.headers.get('host')
    return f"{forwarded_proto}://{host}"


def get_frontend_url(request: Request) -> str:
    """
    Extract the frontend URL for redirects after OAuth callback.
    
    Uses the same protocol and hostname but redirects to port 5000 (UI port).
    """
    forwarded_host = request.headers.get('x-forwarded-host')
    forwarded_proto = request.headers.get('x-forwarded-proto', 'http')
    host = forwarded_host or request.headers.get('host')
    
    # Extract hostname without port
    hostname = host.split(':')[0]
    return f"{forwarded_proto}://{hostname}:5000"