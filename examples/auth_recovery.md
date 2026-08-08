# Auth recovery intent

```intentdsl
INTENT auth_recovery
INPUT api_status integer
INPUT refresh_status integer
STATE retry_count integer = 0
RULE unauthorized
  WHEN api_status == 401
  DO refresh_token
  SET retry_count = retry_count + 1
  ASSERT retry_count <= 2
END
RULE refresh_failed
  WHEN refresh_status == 401 and retry_count >= 1
  EMIT auth_error(reason="refresh_failed")
  STOP
END
FORBID retry_count > 2
OUTPUT auth_recovery_result
```
