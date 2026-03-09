from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse
from loguru import logger as l

from sqlmodels import ResponseBase
import service.oauth
from utils import http_exceptions

callback_router = APIRouter(
    prefix='/callback',
    tags=["callback"],
)

oauth_router = APIRouter(
    prefix='/callback/oauth',
    tags=["callback", "oauth"],
)

upload_router = APIRouter(
    prefix='/callback/upload',
    tags=["callback", "upload"],
)

callback_router.include_router(oauth_router)
callback_router.include_router(upload_router)

@oauth_router.post(
    path='/qq',
    summary='QQ互联回调',
    description='Handle QQ OAuth callback and return user information.',
)
def router_callback_qq() -> ResponseBase:
    """
    Handle QQ OAuth callback and return user information.

    Returns:
        ResponseBase: A model containing the response data for the QQ OAuth callback.
    """
    http_exceptions.raise_not_implemented()

@oauth_router.get(
    path='/github',
    summary='GitHub OAuth 回调',
    description='Handle GitHub OAuth callback and return user information.',
)
async def router_callback_github(
    code: str = Query(description="The token received from GitHub for authentication.")) -> PlainTextResponse:
    """
    GitHub OAuth 回调处理
    - 错误响应示例：
        - {
            'error': 'bad_verification_code',
            'error_description': 'The code passed is incorrect or expired.',
            'error_uri': 'https://docs.github.com/apps/managing-oauth-apps/troubleshooting-oauth-app-access-token-request-errors/#bad-verification-code'
            }

    Returns:
        PlainTextResponse: A response containing the user information from GitHub.
    """
    try:
        access_token = await service.oauth.github.get_access_token(code)
        if not access_token:
            return PlainTextResponse("GitHub 认证失败", status_code=400)

        user_data = await service.oauth.github.get_user_info(access_token.access_token)
        # [TODO] 把 access_token 和 user_data 写数据库，生成 JWT，重定向到前端
        l.info(f"GitHub OAuth 回调成功: user={user_data.user_data.login}")

        return PlainTextResponse("认证成功，功能开发中", status_code=200)
    except Exception as e:
        l.error(f"GitHub OAuth 回调异常: {e}")
        return PlainTextResponse("认证过程中发生错误，请重试", status_code=500)

@upload_router.post(
    path='/remote/{session_id}/{key}',
    summary='远程上传回调',
    description='Handle remote upload callback and return upload status.',
)
def router_callback_remote(session_id: str, key: str) -> ResponseBase:
    """
    Handle remote upload callback and return upload status.

    Args:
        session_id (str): The session ID for the upload.
        key (str): The key for the uploaded file.

    Returns:
        ResponseBase: A model containing the response data for the remote upload callback.
    """
    http_exceptions.raise_not_implemented()

@upload_router.post(
    path='/qiniu/{session_id}',
    summary='七牛云上传回调',
    description='Handle Qiniu Cloud upload callback and return upload status.',
)
def router_callback_qiniu(session_id: str) -> ResponseBase:
    """
    Handle Qiniu Cloud upload callback and return upload status.

    Args:
        session_id (str): The session ID for the upload.

    Returns:
        ResponseBase: A model containing the response data for the Qiniu Cloud upload callback.
    """
    http_exceptions.raise_not_implemented()

@upload_router.post(
    path='/tencent/{session_id}',
    summary='腾讯云上传回调',
    description='Handle Tencent Cloud upload callback and return upload status.',
)
def router_callback_tencent(session_id: str) -> ResponseBase:
    """
    Handle Tencent Cloud upload callback and return upload status.

    Args:
        session_id (str): The session ID for the upload.

    Returns:
        ResponseBase: A model containing the response data for the Tencent Cloud upload callback.
    """
    http_exceptions.raise_not_implemented()

@upload_router.post(
    path='/aliyun/{session_id}',
    summary='阿里云上传回调',
    description='Handle Aliyun upload callback and return upload status.',
)
def router_callback_aliyun(session_id: str) -> ResponseBase:
    """
    Handle Aliyun upload callback and return upload status.

    Args:
        session_id (str): The session ID for the upload.

    Returns:
        ResponseBase: A model containing the response data for the Aliyun upload callback.
    """
    http_exceptions.raise_not_implemented()

@upload_router.post(
    path='/upyun/{session_id}',
    summary='又拍云上传回调',
    description='Handle Upyun upload callback and return upload status.',
)
def router_callback_upyun(session_id: str) -> ResponseBase:
    """
    Handle Upyun upload callback and return upload status.

    Args:
        session_id (str): The session ID for the upload.

    Returns:
        ResponseBase: A model containing the response data for the Upyun upload callback.
    """
    http_exceptions.raise_not_implemented()

@upload_router.post(
    path='/aws/{session_id}',
    summary='AWS S3上传回调',
    description='Handle AWS S3 upload callback and return upload status.',
)
def router_callback_aws(session_id: str) -> ResponseBase:
    """
    Handle AWS S3 upload callback and return upload status.

    Args:
        session_id (str): The session ID for the upload.

    Returns:
        ResponseBase: A model containing the response data for the AWS S3 upload callback.
    """
    http_exceptions.raise_not_implemented()

@upload_router.post(
    path='/onedrive/finish/{session_id}',
    summary='OneDrive上传完成回调',
    description='Handle OneDrive upload completion callback and return upload status.',
)
def router_callback_onedrive_finish(session_id: str) -> ResponseBase:
    """
    Handle OneDrive upload completion callback and return upload status.

    Args:
        session_id (str): The session ID for the upload.

    Returns:
        ResponseBase: A model containing the response data for the OneDrive upload completion callback.
    """
    http_exceptions.raise_not_implemented()

@upload_router.get(
    path='/ondrive/auth',
    summary='OneDrive授权回调',
    description='Handle OneDrive authorization callback and return authorization status.',
)
def router_callback_onedrive_auth() -> ResponseBase:
    """
    Handle OneDrive authorization callback and return authorization status.

    Returns:
        ResponseBase: A model containing the response data for the OneDrive authorization callback.
    """
    http_exceptions.raise_not_implemented()

@upload_router.get(
    path='/google/auth',
    summary='Google OAuth 完成',
    description='Handle Google OAuth completion callback and return authorization status.',
)
def router_callback_google_auth() -> ResponseBase:
    """
    Handle Google OAuth completion callback and return authorization status.

    Returns:
        ResponseBase: A model containing the response data for the Google OAuth completion callback.
    """
    http_exceptions.raise_not_implemented()
