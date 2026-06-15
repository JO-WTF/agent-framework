import os

DOCKER_PROXY_ENV_VARS = (
    "http_proxy",
    "https_proxy",
    "no_proxy",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "NO_PROXY",
)


def configured_proxy_env_vars() -> list[str]:
    """Return proxy environment variable names that are configured on the host."""
    return [name for name in DOCKER_PROXY_ENV_VARS if os.getenv(name)]


def docker_build_proxy_args() -> list[str]:
    """Return docker build args that forward host proxy environment values."""
    args: list[str] = []
    for name in configured_proxy_env_vars():
        args.extend(["--build-arg", name])
    return args


def docker_run_proxy_env_args() -> list[str]:
    """Return docker run env args that forward host proxy environment values."""
    args: list[str] = []
    for name in configured_proxy_env_vars():
        args.extend(["-e", name])
    return args
