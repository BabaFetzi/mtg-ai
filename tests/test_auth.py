import pytest
from datetime import timedelta
import time
from fastapi import HTTPException
from auth import (
    hash_passwort,
    verify_passwort,
    create_access_token,
    create_refresh_token,
    decode_token,
    check_login_rate_limit,
    record_login_attempt,
    login_attempts
)

def test_password_hashing():
    pw = "SuperSecurePassword123"
    hashed = hash_passwort(pw)
    assert hashed != pw
    assert verify_passwort(pw, hashed) is True
    assert verify_passwort("WrongPassword", hashed) is False

def test_jwt_generation_and_decoding():
    data = {"sub": "testuser", "role": "premium"}
    
    # Access token
    token = create_access_token(data)
    decoded = decode_token(token)
    assert decoded is not None
    assert decoded["sub"] == "testuser"
    assert decoded["role"] == "premium"
    assert "exp" in decoded

    # Expired token
    expired_token = create_access_token(data, expires_delta=timedelta(seconds=-10))
    assert decode_token(expired_token) is None

    # Refresh token
    refresh_token = create_refresh_token(data)
    decoded_refresh = decode_token(refresh_token)
    assert decoded_refresh is not None
    assert decoded_refresh["sub"] == "testuser"

def test_login_rate_limiting():
    ip = "192.168.1.1"
    user = "hacker"
    key = (ip, user)
    
    # Clear any previous attempts
    if key in login_attempts:
        del login_attempts[key]
        
    # First 4 attempts should not raise anything
    for _ in range(4):
        record_login_attempt(ip, user, success=False)
        check_login_rate_limit(ip, user)
        
    # 5th attempt should raise HTTPException (429)
    with pytest.raises(HTTPException) as exc_info:
        record_login_attempt(ip, user, success=False)
    assert exc_info.value.status_code == 429
    assert "gesperrt" in exc_info.value.detail

    # Subsequent check should raise 429
    with pytest.raises(HTTPException) as exc_info:
        check_login_rate_limit(ip, user)
    assert exc_info.value.status_code == 429

    # Successful login resets the rate limit
    # Manipulate attempts to mock success
    login_attempts[key] = (0, 0.0)
    record_login_attempt(ip, user, success=True)
    assert key not in login_attempts
