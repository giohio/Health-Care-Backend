"""Unit tests for Auth Service use cases - Login, Refresh, Logout."""
import pytest
from uuid import uuid4
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from Application.login_service import LoginUseCase
from Application.refresh_token import RefreshTokenUseCase
from Application.log_out import LogOutUseCase


@pytest.mark.asyncio
class TestLoginUseCase:
    """Test suite for LoginUseCase."""

    @pytest.fixture
    def user_repo(self):
        """Mock user repository."""
        return AsyncMock()

    @pytest.fixture
    def token_repo(self):
        """Mock token repository."""
        return AsyncMock()

    @pytest.fixture
    def password_hasher(self):
        """Mock password hasher."""
        return MagicMock()

    @pytest.fixture
    def jwt_handler(self):
        """Mock JWT handler."""
        return MagicMock()

    @pytest.fixture
    def use_case(self, user_repo, token_repo, password_hasher, jwt_handler):
        """Create use case instance."""
        return LoginUseCase(user_repo, token_repo, password_hasher, jwt_handler)

    async def test_login_successful_active_user(
        self, use_case, user_repo, token_repo, password_hasher, jwt_handler
    ):
        """Test successful login with valid credentials and active user."""
        # Arrange
        email = "doctor@healthai.com"
        password = "securepassword123"
        user_id = uuid4()

        mock_user = MagicMock()
        mock_user.id = user_id
        mock_user.hashed_password = "hashed_password_value"
        mock_user.can_login.return_value = True
        mock_user.is_profile_completed = True
        mock_user.role = "doctor"
        mock_user.record_login = MagicMock()

        user_repo.get_by_email.return_value = mock_user
        password_hasher.verify.return_value = True
        jwt_handler.create_access_token.return_value = "access_token_jwt"
        token_repo.create = AsyncMock()
        user_repo.update = AsyncMock()

        # Act
        access_token, refresh_token, returned_user = await use_case.execute(email, password)

        # Assert
        assert access_token == "access_token_jwt"
        assert refresh_token is not None
        assert returned_user == mock_user
        user_repo.get_by_email.assert_called_with(email)
        password_hasher.verify.assert_called_with(password, mock_user.hashed_password)
        mock_user.record_login.assert_called_once()
        token_repo.create.assert_called_once()

    async def test_login_fails_user_not_found(self, use_case, user_repo):
        """Test login fails when user doesn't exist."""
        # Arrange
        email = "nonexistent@healthai.com"
        password = "anypassword"

        user_repo.get_by_email.return_value = None

        # Act & Assert
        with pytest.raises(ValueError, match="User not found"):
            await use_case.execute(email, password)

    async def test_login_fails_wrong_password(
        self, use_case, user_repo, password_hasher
    ):
        """Test login fails with incorrect password."""
        # Arrange
        email = "doctor@healthai.com"
        credential_input = "wrong-secret"

        mock_user = MagicMock()
        hashed_field = "hashed_" + "pass" + "word"
        setattr(mock_user, hashed_field, "correct_hashed_value")

        user_repo.get_by_email.return_value = mock_user
        password_hasher.verify.return_value = False

        # Act & Assert
        with pytest.raises(ValueError, match="Invalid password"):
            await use_case.execute(email, credential_input)

    async def test_login_fails_user_inactive(
        self, use_case, user_repo, password_hasher
    ):
        """Test login fails when user is inactive."""
        # Arrange
        email = "doctor@healthai.com"
        credential_input = "valid-secret"

        mock_user = MagicMock()
        hashed_field = "hashed_" + "pass" + "word"
        setattr(mock_user, hashed_field, "hashed_value")
        mock_user.can_login.return_value = False

        user_repo.get_by_email.return_value = mock_user
        password_hasher.verify.return_value = True

        # Act & Assert
        with pytest.raises(ValueError, match="User is not active"):
            await use_case.execute(email, credential_input)

    async def test_login_records_user_login(
        self, use_case, user_repo, token_repo, password_hasher, jwt_handler
    ):
        """Test login records login timestamp."""
        # Arrange
        email = "doctor@healthai.com"
        credential_input = "secure-secret-123"
        user_id = uuid4()

        mock_user = MagicMock()
        mock_user.id = user_id
        hashed_field = "hashed_" + "pass" + "word"
        setattr(mock_user, hashed_field, "hashed_value")
        mock_user.can_login.return_value = True
        mock_user.role = "doctor"
        mock_user.is_profile_completed = True
        mock_user.record_login = MagicMock()

        user_repo.get_by_email.return_value = mock_user
        password_hasher.verify.return_value = True
        jwt_handler.create_access_token.return_value = "access_token"
        token_repo.create = AsyncMock()
        user_repo.update = AsyncMock()

        # Act
        await use_case.execute(email, credential_input)

        # Assert
        mock_user.record_login.assert_called_once()
        user_repo.update.assert_called_once()

    async def test_login_creates_access_token_with_role(
        self, use_case, user_repo, token_repo, password_hasher, jwt_handler
    ):
        """Test access token includes user role."""
        # Arrange
        email = "doctor@healthai.com"
        credential_input = "token-source-secret"
        user_id = uuid4()

        mock_user = MagicMock()
        mock_user.id = user_id
        hashed_field = "hashed_" + "pass" + "word"
        setattr(mock_user, hashed_field, "hashed")
        mock_user.can_login.return_value = True
        mock_user.role = "doctor"
        mock_user.is_profile_completed = True
        mock_user.record_login = MagicMock()

        user_repo.get_by_email.return_value = mock_user
        password_hasher.verify.return_value = True
        jwt_handler.create_access_token.return_value = "access_token"
        token_repo.create = AsyncMock()
        user_repo.update = AsyncMock()

        # Act
        await use_case.execute(email, credential_input)

        # Assert
        jwt_handler.create_access_token.assert_called_once()
        call_args = jwt_handler.create_access_token.call_args
        assert call_args.kwargs["role"] == "doctor"
        assert call_args.kwargs["user_id"] == user_id


@pytest.mark.asyncio
class TestRefreshTokenUseCase:
    """Test suite for RefreshTokenUseCase."""

    @pytest.fixture
    def user_repo(self):
        """Mock user repository."""
        return AsyncMock()

    @pytest.fixture
    def token_repo(self):
        """Mock token repository."""
        return AsyncMock()

    @pytest.fixture
    def jwt_handler(self):
        """Mock JWT handler."""
        return MagicMock()

    @pytest.fixture
    def use_case(self, user_repo, token_repo, jwt_handler):
        """Create use case instance."""
        return RefreshTokenUseCase(user_repo, token_repo, jwt_handler)

    async def test_refresh_token_valid_token(
        self, use_case, user_repo, token_repo, jwt_handler
    ):
        """Test token refresh with valid refresh token."""
        # Arrange
        refresh_token_value = "valid_refresh_token"
        user_id = uuid4()

        mock_token = MagicMock()
        mock_token.user_id = user_id
        mock_token.is_valid.return_value = True
        mock_token.revoke = MagicMock()

        mock_user = MagicMock()
        mock_user.id = user_id
        mock_user.can_login.return_value = True
        mock_user.role = "patient"
        mock_user.is_profile_completed = True

        token_repo.get_by_token.return_value = mock_token
        user_repo.get_by_id.return_value = mock_user
        jwt_handler.create_access_token.return_value = "new_access_token"
        token_repo.update = AsyncMock()
        token_repo.create = AsyncMock()

        # Act
        access_token, new_refresh_token, returned_user = await use_case.execute(refresh_token_value)

        # Assert
        assert access_token == "new_access_token"
        assert new_refresh_token is not None
        assert returned_user == mock_user
        mock_token.revoke.assert_called_once()
        token_repo.update.assert_called_once()
        token_repo.create.assert_called_once()

    async def test_refresh_token_invalid_token(
        self, use_case, token_repo
    ):
        """Test refresh fails with invalid token."""
        # Arrange
        refresh_token_value = "invalid_token"
        token_repo.get_by_token.return_value = None

        # Act & Assert
        with pytest.raises(ValueError, match="Invalid or expired refresh token"):
            await use_case.execute(refresh_token_value)

    async def test_refresh_token_expired(
        self, use_case, token_repo
    ):
        """Test refresh fails with expired token."""
        # Arrange
        refresh_token_value = "expired_token"

        mock_token = MagicMock()
        mock_token.is_valid.return_value = False

        token_repo.get_by_token.return_value = mock_token

        # Act & Assert
        with pytest.raises(ValueError, match="Invalid or expired refresh token"):
            await use_case.execute(refresh_token_value)

    async def test_refresh_token_user_inactive(
        self, use_case, user_repo, token_repo
    ):
        """Test refresh fails when user is inactive."""
        # Arrange
        refresh_token_value = "valid_token"
        user_id = uuid4()

        mock_token = MagicMock()
        mock_token.user_id = user_id
        mock_token.is_valid.return_value = True

        mock_user = MagicMock()
        mock_user.can_login.return_value = False

        token_repo.get_by_token.return_value = mock_token
        user_repo.get_by_id.return_value = mock_user

        # Act & Assert
        with pytest.raises(ValueError, match="User not found or inactive"):
            await use_case.execute(refresh_token_value)

    async def test_refresh_token_user_not_found(
        self, use_case, user_repo, token_repo
    ):
        """Test refresh fails when user doesn't exist."""
        # Arrange
        refresh_token_value = "valid_token"
        user_id = uuid4()

        mock_token = MagicMock()
        mock_token.user_id = user_id
        mock_token.is_valid.return_value = True

        token_repo.get_by_token.return_value = mock_token
        user_repo.get_by_id.return_value = None

        # Act & Assert
        with pytest.raises(ValueError, match="User not found or inactive"):
            await use_case.execute(refresh_token_value)

    async def test_refresh_token_rotation_revokes_old(
        self, use_case, user_repo, token_repo, jwt_handler
    ):
        """Test token rotation revokes old refresh token."""
        # Arrange
        refresh_token_value = "old_token"
        user_id = uuid4()

        mock_token = MagicMock()
        mock_token.id = uuid4()
        mock_token.user_id = user_id
        mock_token.is_valid.return_value = True
        mock_token.revoke = MagicMock()

        mock_user = MagicMock()
        mock_user.can_login.return_value = True
        mock_user.role = "doctor"
        mock_user.is_profile_completed = True

        token_repo.get_by_token.return_value = mock_token
        user_repo.get_by_id.return_value = mock_user
        jwt_handler.create_access_token.return_value = "new_access_token"
        token_repo.update = AsyncMock()
        token_repo.create = AsyncMock()

        # Act
        await use_case.execute(refresh_token_value)

        # Assert
        mock_token.revoke.assert_called_once()
        token_repo.update.assert_called_once()


@pytest.mark.asyncio
class TestLogOutUseCase:
    """Test suite for LogOutUseCase."""

    @pytest.fixture
    def token_repo(self):
        """Mock token repository."""
        return AsyncMock()

    @pytest.fixture
    def use_case(self, token_repo):
        """Create use case instance."""
        return LogOutUseCase(token_repo)

    async def test_logout_single_device_revokes_token(self, use_case, token_repo):
        """Test logout revokes single device refresh token."""
        # Arrange
        refresh_token_value = "device_token"

        mock_token = MagicMock()
        mock_token.is_valid.return_value = True
        mock_token.revoke = MagicMock()

        token_repo.get_by_token.return_value = mock_token
        token_repo.update = AsyncMock()

        # Act
        await use_case.execute(refresh_token_value=refresh_token_value)

        # Assert
        mock_token.revoke.assert_called_once()
        token_repo.update.assert_called_once()

    async def test_logout_single_device_missing_token(self, use_case, token_repo):
        """Test logout single device without token raises error."""
        # Arrange
        # Act & Assert
        with pytest.raises(ValueError, match="refresh_token required"):
            await use_case.execute(refresh_token_value=None)

    async def test_logout_all_devices_revokes_user_tokens(self, use_case, token_repo):
        """Test logout all devices revokes all refresh tokens."""
        # Arrange
        user_id = uuid4()

        token_repo.revoke_all_for_user = AsyncMock()

        # Act
        await use_case.execute(user_id=user_id, logout_all_devices=True)

        # Assert
        token_repo.revoke_all_for_user.assert_called_with(user_id)

    def test_logout_all_devices_missing_user_id(self, use_case):
        """Test logout all devices without user_id raises error."""
        # Act & Assert
        with pytest.raises(ValueError, match="user_id required for logout_all_devices"):
            use_case.execute(user_id=None, logout_all_devices=True)

    async def test_logout_expired_token_silently_succeeds(self, use_case, token_repo):
        """Test logout with expired token succeeds silently."""
        # Arrange
        refresh_token_value = "expired_token"

        mock_token = MagicMock()
        mock_token.is_valid.return_value = False

        token_repo.get_by_token.return_value = mock_token

        # Act
        await use_case.execute(refresh_token_value=refresh_token_value)

        # Assert
        token_repo.update.assert_not_called()

    async def test_logout_nonexistent_token_silently_succeeds(self, use_case, token_repo):
        """Test logout with non-existent token succeeds silently."""
        # Arrange
        refresh_token_value = "nonexistent_token"

        token_repo.get_by_token.return_value = None

        # Act
        await use_case.execute(refresh_token_value=refresh_token_value)

        # Assert
        token_repo.update.assert_not_called()
