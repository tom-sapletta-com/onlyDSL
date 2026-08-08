from contextdsl import ContextCompiler, DslContextEvent


def build_llm_context() -> str:
    compiler = ContextCompiler(
        name="auth_failure_context",
        origin="api_gateway",
        purpose="failure_analysis",
        trace_id="req_7f21",
    )
    compiler.capability("action", "refresh_token")
    compiler.capability("event", "auth_error")
    compiler.state("api_status", 401)
    compiler.state("refresh_status", 401)
    compiler.metric("request_latency_ms", 83.4)

    # Preferred: the application emits semantic events from the start.
    compiler.event(DslContextEvent(
        source="auth_service",
        code="request_unauthorized",
        severity="error",
        fields={"status": 401, "attempt": 1},
    ))
    compiler.event(DslContextEvent(
        source="auth_service",
        code="token_refresh_failed",
        severity="error",
        fields={"status": 401, "attempt": 1},
    ))
    return compiler.to_markdown()


if __name__ == "__main__":
    print(build_llm_context())
