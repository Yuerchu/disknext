from fastapi import APIRouter

from models import MCPRequestBase, MCPResponseBase, MCPMethod

# MCP 路由
MCP_router = APIRouter(
    prefix='/mcp',
    tags=["mcp"],
)

@MCP_router.get(
        "/",
)
async def mcp_root(
    param: MCPRequestBase
):
    match param.method:
        case MCPMethod.PING:
            return MCPResponseBase(result="pong", **param.model_dump())