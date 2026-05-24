import json

from fastapi import Request


class RequestLoggerMiddleware:
    def __init__(self, app):
        @app.middleware("http")
        async def print_request_details(request: Request, call_next):
            print(f"{request.method} {request.url.path}")
            print(f"Query params: {dict(request.query_params)}")
            try:
                body = await request.body()
                if body:
                    try:
                        body_json = json.loads(body)
                        print(f"Body:\n{json.dumps(body_json, indent=2)}")
                    except Exception:
                        print(f"Body (raw): {body.decode('utf-8')[:500]}")
                else:
                    print("Body: <empty>")
            except Exception as e:
                print(f"Could not read body: {e}")
            response = await call_next(request)
            return response
