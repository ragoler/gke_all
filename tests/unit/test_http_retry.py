import pytest
import asyncio
import httpx
from unittest.mock import AsyncMock, patch
from showcase_admin.app.k8s_client import execute_http_with_retry

@pytest.mark.anyio
async def test_execute_http_with_retry_success_after_502():
    req = httpx.Request("POST", "http://test.local")
    resp_502 = httpx.Response(502, request=req)
    resp_200 = httpx.Response(200, json={"reply": "ok"}, request=req)
    
    mock_post = AsyncMock(side_effect=[resp_502, resp_502, resp_200])
    
    with patch("httpx.AsyncClient.post", mock_post), patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        result = await execute_http_with_retry("POST", "http://test.local", json_payload={"test": "data"}, max_retries=3, timeout=10.0)
        
        assert result.status_code == 200
        assert result.json() == {"reply": "ok"}
        assert mock_post.call_count == 3
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(2)
        mock_sleep.assert_any_call(4)

@pytest.mark.anyio
async def test_execute_http_with_retry_persistent_502():
    req = httpx.Request("GET", "http://test.local")
    resp_502 = httpx.Response(502, request=req)
    
    mock_get = AsyncMock(return_value=resp_502)
    
    with patch("httpx.AsyncClient.get", mock_get), patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        with pytest.raises((httpx.RequestError, httpx.HTTPError)):
            await execute_http_with_retry("GET", "http://test.local", max_retries=2, timeout=10.0)
            
        assert mock_get.call_count == 3
        assert mock_sleep.call_count == 2

