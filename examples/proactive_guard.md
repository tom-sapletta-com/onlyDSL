# Intent contract: proactive guard

```intentdsl
INTENT deployment_guard
INPUT error_rate number
INPUT rollback_ready boolean
STATE blocked boolean = false
RULE risk_detected
  WHEN error_rate >= 0.05
  EMIT deployment_risk(level="high")
  SET blocked = true
END
RULE rollback
  WHEN blocked == true and rollback_ready == true
  DO rollback_release
  EMIT rollback_started(reason="error_rate")
  STOP
END
FORBID error_rate >= 0.05 and blocked == false
OUTPUT deployment_decision
```
