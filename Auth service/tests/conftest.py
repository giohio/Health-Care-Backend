import pytest
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


@pytest.fixture(scope="session", autouse=True)
def patch_jwt_private_key_path(tmp_path_factory):
    """Patch jwt_handler.private_key_path to a temp RSA key so JWTHandler can be instantiated in unit tests."""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend(),
    )
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )

    key_path = tmp_path_factory.mktemp("keys") / "private.pem"
    key_path.write_bytes(private_pem)

    import infrastructure.security.jwt_handler as jwt_handler_module
    from presentation.dependencies import get_jwt_handler

    original_path = jwt_handler_module.private_key_path
    jwt_handler_module.private_key_path = str(key_path)
    get_jwt_handler.cache_clear()

    yield

    jwt_handler_module.private_key_path = original_path
    get_jwt_handler.cache_clear()
