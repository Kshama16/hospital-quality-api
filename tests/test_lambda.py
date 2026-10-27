"""Invokes the Lambda handler with an API Gateway HTTP API (payload v2.0) event."""

import json

from app.lambda_handler import handler


def event(path: str, query: str = "") -> dict:
    return {
        "version": "2.0",
        "routeKey": "$default",
        "rawPath": path,
        "rawQueryString": query,
        "headers": {"host": "api.example.com", "x-api-key": "lambda-test"},
        "requestContext": {
            "http": {"method": "GET", "path": path, "protocol": "HTTP/1.1", "sourceIp": "1.2.3.4"},
            "domainName": "api.example.com",
            "requestId": "r1",
            "stage": "$default",
        },
        "isBase64Encoded": False,
    }


class Ctx:
    function_name, aws_request_id = "hospital-quality-api", "r1"


def test_lambda_handler_serves_api_gateway_events():
    r = handler(event("/hospitals/220071"), Ctx())
    assert r["statusCode"] == 200 and json.loads(r["body"])["name"] == "Massachusetts General Hospital"
    r = handler(event("/rankings/sepsis_care_pct", "state=MA&k=3"), Ctx())
    body = json.loads(r["body"])
    assert r["statusCode"] == 200 and len(body["items"]) == 3
