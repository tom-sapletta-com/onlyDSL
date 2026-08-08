# Runtime-generated context example

```contextdsl
CONTEXT auth_failure_context
VERSION 1
ORIGIN api_gateway
PURPOSE failure_analysis
TRACE "req_7f21"
POLICY dsl_only_llm true
POLICY raw_context_forbidden true
CAPABILITY action refresh_token
CAPABILITY event auth_error
STATE api_status integer = 401
STATE refresh_status integer = 401
METRIC request_latency_ms = 83.4
RECORD event auth_service request_unauthorized
  FIELD attempt = 1
  FIELD severity = "error"
  FIELD status = 401
END
RECORD event auth_service token_refresh_failed
  FIELD attempt = 1
  FIELD severity = "error"
  FIELD status = 401
END
END_CONTEXT
```
