Use python 3.11, and latest versions of fastapi and pydantic for the api.
Use SOLID and KISS programming principals.

This project consists of mcp_server.py which implements an mcp server suitable for use 
with compatiable llms such as claude.ai
This contains tools which calls a rest api functions. 

The rest_api server is defined in the remote_server.py, which uses FastAPI to create rest endpoints.
End points are grouped into routers and made accessible to the mcp_server.py
